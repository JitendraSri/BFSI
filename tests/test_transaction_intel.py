import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import jwt
import numpy as np
import pandas as pd
import pymongo

with patch.object(pymongo, 'MongoClient'):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app as application


def synthetic_transactions(rows=1500, seed=3):
    rng = np.random.default_rng(seed)
    fraud = rng.random(rows) < 0.06
    return pd.DataFrame({
        'transaction_amount': np.where(fraud, rng.uniform(40000, 90000, rows), rng.uniform(100, 8000, rows)),
        'channel': np.where(fraud, rng.choice(['ATM', 'IMPS'], rows), rng.choice(['UPI', 'CARD', 'NEFT'], rows)),
        'account_age_days': np.where(fraud, rng.integers(0, 20, rows), rng.integers(30, 2000, rows)),
        'kyc_verified': np.where(fraud, 0, rng.integers(0, 2, rows)),
        'is_fraud': fraud.astype(int),
    })


class TransactionIntelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.encoder, cls.bundle, cls.metrics = application.train_models(synthetic_transactions())

    def test_training_reports_imbalanced_classification_metrics(self):
        for detector in ('random_forest', 'anomaly_detector', 'hybrid_risk'):
            result = self.metrics[detector]
            self.assertTrue(0 <= result['roc_auc'] <= 1)
            self.assertTrue(0 <= result['pr_auc'] <= 1)
            self.assertIn('false_positive_rate', result)
            self.assertEqual(set(result['confusion_matrix']), {'tn', 'fp', 'fn', 'tp'})
        self.assertGreater(self.metrics['random_forest']['roc_auc'], 0.9)
        self.assertIn('single_p95', self.metrics['detection_latency_ms'])
        self.assertTrue(0.05 <= self.metrics['decision_threshold'] <= 0.95)

    def test_scoring_explains_risky_transactions(self):
        frame = pd.DataFrame([
            {'transaction_amount': 85000, 'channel': 'ATM', 'account_age_days': 3, 'kyc_verified': 0, 'timestamp': '2026-10-01T02:30:00'},
            {'transaction_amount': 900, 'channel': 'UPI', 'account_age_days': 900, 'kyc_verified': 1, 'timestamp': '2026-10-01T12:00:00'},
        ])
        history = {'median_amount': 1000.0, 'channels': {'UPI': 40}, 'count': 40}
        scored = application.score_transactions(self.model, self.encoder, self.bundle, frame, history)
        risky, normal = scored.iloc[0], scored.iloc[1]
        self.assertGreater(risky['risk_score'], normal['risk_score'])
        self.assertEqual(risky['risk_level'], 'High')
        reasons = ' '.join(risky['risk_reasons'])
        self.assertIn('typical transaction', reasons)
        self.assertIn('KYC not verified', reasons)
        self.assertIn('midnight', reasons)
        self.assertIn('rarely used', reasons)

    def test_velocity_check_flags_rapid_fire_transactions_in_the_same_batch(self):
        base = pd.Timestamp('2026-10-01T10:00:00')
        frame = pd.DataFrame([
            {'transaction_amount': 500, 'channel': 'UPI', 'account_age_days': 400, 'kyc_verified': 1, 'timestamp': base},
            {'transaction_amount': 500, 'channel': 'UPI', 'account_age_days': 400, 'kyc_verified': 1, 'timestamp': base + pd.Timedelta(minutes=2)},
            {'transaction_amount': 500, 'channel': 'UPI', 'account_age_days': 400, 'kyc_verified': 1, 'timestamp': base + pd.Timedelta(minutes=4)},
            {'transaction_amount': 500, 'channel': 'UPI', 'account_age_days': 400, 'kyc_verified': 1, 'timestamp': base + pd.Timedelta(minutes=6)},
        ])
        scored = application.score_transactions(self.model, self.encoder, self.bundle, frame)
        self.assertIn('rapid activity', ' '.join(scored.iloc[0]['risk_reasons']))

        isolated = pd.DataFrame([{'transaction_amount': 500, 'channel': 'UPI', 'account_age_days': 400, 'kyc_verified': 1, 'timestamp': base}])
        scored_isolated = application.score_transactions(self.model, self.encoder, self.bundle, isolated)
        self.assertNotIn('rapid activity', ' '.join(scored_isolated.iloc[0]['risk_reasons']))

    def test_velocity_check_counts_the_customers_recent_history(self):
        base = pd.Timestamp('2026-10-01T10:00:00')
        frame = pd.DataFrame([{'transaction_amount': 500, 'channel': 'UPI', 'account_age_days': 400, 'kyc_verified': 1, 'timestamp': base}])
        history = {'recent_timestamps': [base - pd.Timedelta(minutes=1), base - pd.Timedelta(minutes=3), base - pd.Timedelta(minutes=5)]}
        scored = application.score_transactions(self.model, self.encoder, self.bundle, frame, history)
        self.assertIn('rapid activity', ' '.join(scored.iloc[0]['risk_reasons']))

    def test_unseen_channels_do_not_break_scoring(self):
        frame = pd.DataFrame([{'transaction_amount': 500, 'channel': 'Crypto', 'account_age_days': 100, 'kyc_verified': 1}])
        scored = application.score_transactions(self.model, self.encoder, None, frame)
        self.assertEqual(scored.iloc[0]['anomaly_score'], 0)

    def test_training_requires_both_classes(self):
        frame = synthetic_transactions()
        frame['is_fraud'] = 0
        with self.assertRaises(ValueError):
            application.train_models(frame)

    def test_predict_endpoint_returns_risk_and_reasons(self):
        token = jwt.encode({'user_id': 'u1'}, application.SECRET_KEY, algorithm='HS256')
        database = Mock()
        database.transactions.find.return_value.sort.return_value.limit.return_value = []
        application.limiter.enabled = False
        self.addCleanup(setattr, application.limiter, 'enabled', True)
        with patch.object(application, 'ml_model', self.model), patch.object(application, 'encoder', self.encoder), \
                patch.object(application, 'anomaly_bundle', self.bundle), patch.object(application, 'get_db', return_value=database):
            response = application.app.test_client().post('/api/predict', headers={'Authorization': 'Bearer ' + token},
                                                          json={'amount': 80000, 'channel': 'ATM', 'account_age': 2, 'kyc_verified': 'No'})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['risk_level'], 'High')
        self.assertTrue(body['reasons'])
        self.assertIn('threshold', body)


class IngestSecurityTests(unittest.TestCase):
    def test_private_and_non_http_urls_are_refused(self):
        for url in ('http://127.0.0.1/admin', 'http://localhost:5000/', 'file:///etc/passwd', 'http://169.254.169.254/latest/meta-data',
                    'http://10.0.0.5/report.pdf', 'ftp://example.com/x.pdf'):
            with self.subTest(url=url), self.assertRaises(application.IngestError):
                application.fetch(url)

    def test_redirects_to_private_hosts_are_refused(self):
        handler = application._SafeRedirectHandler()
        with self.assertRaises(application.IngestError):
            handler.redirect_request(Mock(), None, 302, 'Found', {}, 'http://127.0.0.1/secret')

    def test_sec_requires_contact_user_agent(self):
        with patch.dict('os.environ', {'SEC_USER_AGENT': ''}):
            with self.assertRaises(application.IngestError):
                application.latest_filings('AAPL')

    def test_filename_detection(self):
        self.assertEqual(application.filename_for('https://x.com/a/Annual Report 2024.pdf', 'application/pdf', b'%PDF-1.7'), 'Annual_Report_2024.pdf')
        with self.assertRaises(application.IngestError):
            application.filename_for('https://x.com/a.zip', 'application/zip', b'PK')


class RagRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.headers = {'Authorization': 'Bearer ' + jwt.encode({'user_id': 'u1'}, application.SECRET_KEY, algorithm='HS256')}

    def test_ask_rejects_bad_options_and_ids(self):
        bad_options = self.client.post('/api/rag/ask', headers=self.headers, json={'query': 'q', 'document_id': 'all', 'options': 'turbo'})
        self.assertEqual(bad_options.status_code, 400)
        bad_id = self.client.post('/api/rag/ask', headers=self.headers, json={'query': 'q', 'document_id': '../x'})
        self.assertEqual(bad_id.status_code, 404)

    def test_url_ingest_refuses_private_network(self):
        application.limiter.enabled = False
        self.addCleanup(setattr, application.limiter, 'enabled', True)
        response = self.client.post('/api/rag/ingest/url', headers=self.headers, json={'url': 'http://127.0.0.1:5000/test_db'})
        self.assertEqual(response.status_code, 400)

    def test_evaluation_endpoint_returns_reports(self):
        response = self.client.get('/api/rag/evaluation', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('reports', response.get_json())


if __name__ == '__main__':
    unittest.main()
