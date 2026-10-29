import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime

from unittest.mock import Mock, patch

import jwt
import pandas as pd
import pymongo


with patch.object(pymongo, 'MongoClient'):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app as application


class _StrictDatabase:
    """Mimics pymongo.Database, which raises when used in a boolean context."""

    def __init__(self):
        self.users = Mock()
        self.users.find_one.return_value = {'user_id': 'owner-1', 'kyc_status': 'Verified', 'created_at': datetime(2020, 1, 1)}
        self.transactions = Mock()

    def __bool__(self):
        raise NotImplementedError('Database objects do not implement truth value testing')


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.token = jwt.encode({'user_id': 'owner-1', 'email': 'owner@example.test'}, application.SECRET_KEY, algorithm='HS256')
        self.headers = {'Authorization': 'Bearer ' + self.token}
        # These tests call rate-limited endpoints repeatedly.
        application.limiter.enabled = False
        self.addCleanup(setattr, application.limiter, 'enabled', True)

    def test_unknown_html_page_returns_404(self):
        self.assertEqual(self.client.get('/no-such-page.html').status_code, 404)

    def test_diagnostic_endpoints_are_hidden_by_default(self):
        with patch.object(application, 'DIAGNOSTICS_ENABLED', False):
            self.assertEqual(self.client.get('/test_db').status_code, 404)
            self.assertEqual(self.client.get('/test-atlas').status_code, 404)

    def test_single_analyze_route_is_registered(self):
        rules = [rule for rule in application.app.url_map.iter_rules() if rule.rule == '/api/analyze']
        self.assertEqual(len(rules), 1)

    def test_column_remap_works_with_real_database_and_original_headers(self):
        raw = pd.DataFrame([
            {'ref': 'A-1', 'net': '100.00', 'when': '2026-10-01'},
            {'ref': 'A-1', 'net': '120.00', 'when': '2026-10-01'},
            {'ref': 'A-2', 'net': 'oops', 'when': '2026-10-02'},
        ])
        staged = {
            'rows': '[]',
            'raw_rows': raw.to_json(orient='records'),
            'file_name': 'bank.csv', 'import_batch_id': 'b', 'rows_detected': 3,
            'rejected_rows': 0, 'duplicate_rows': 0, 'invalid_rows_csv': '',
            'explanation': '', 'risk_percentage': 0,
        }
        with patch.object(application, 'get_db', return_value=_StrictDatabase()), \
                patch.object(application.cache, 'get', return_value=staged), \
                patch.object(application.cache, 'set'):
            response = self.client.post('/upload/map', headers=self.headers, json={
                'preview_id': 'a' * 32,
                'column_map': {'ref': 'transaction_id', 'net': 'transaction_amount', 'when': 'timestamp'},
            })
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload['valid_rows'], 1)
        self.assertEqual(payload['rejected'], 1)
        self.assertEqual(payload['duplicates_skipped'], 1)
        self.assertEqual(payload['duplicate_review'], [{'transaction_id': 'A-1', 'rows': [2, 3]}])
        self.assertEqual(payload['preview'][0]['transaction_amount'], 120.0)

    def test_upload_reports_duplicate_rows_before_dropping_them(self):
        database = Mock()
        database.users.find_one.return_value = {'user_id': 'owner-1', 'kyc_status': 'Verified', 'created_at': datetime(2020, 1, 1)}
        csv = b"transaction_id,amount,date\nD-1,10,2026-10-01\nD-1,12,2026-10-01\nD-2,5,2026-10-02\n"
        with patch.object(application, 'get_db', return_value=database), patch.object(application.cache, 'set'):
            response = self.client.post('/upload', headers=self.headers, content_type='multipart/form-data',
                                        data={'file': (io.BytesIO(csv), 'ledger.csv')})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['duplicate_review'], [{'transaction_id': 'D-1', 'rows': [2, 3]}])

    def test_parse_money_rejects_non_finite_negative_and_garbage_amounts(self):
        for amount in ('NaN', 'inf', -5, 0, 'abc', None):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                application.parse_money(amount)
        self.assertEqual(application.parse_money('10.5'), 10.5)
        self.assertEqual(application.parse_money(0, allow_zero=True), 0)

    def test_simulated_money_movement_endpoints_are_gone(self):
        registered = {rule.rule for rule in application.app.url_map.iter_rules()}
        for path in ('/api/transfer', '/api/loan/apply', '/api/insurance/apply', '/api/chat',
                     '/api/profile/kyc', '/api/profile/kyc/confirm', '/api/profile/kyc/resend-otp'):
            with self.subTest(path=path):
                self.assertNotIn(path, registered)

    def test_register_validates_fields_and_normalizes_email(self):
        database = Mock()
        database.users.find_one.return_value = None
        with patch.object(application, 'get_db', return_value=database), \
                patch.object(application, 'send_otp_email', return_value=True):
            missing = self.client.post('/register', json={'email': 'a@b.co'})
            too_long = self.client.post('/register', json={'name': 'A', 'email': 'a@b.co', 'password': 'x' * 73})
            created = self.client.post('/register', json={'name': 'A', 'email': ' Mixed@Example.COM ', 'password': 'long-enough'})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(database.users.insert_one.call_args.args[0]['email'], 'mixed@example.com')

    def test_login_finds_legacy_mixed_case_email(self):
        password_hash = application.bcrypt.hashpw(b'correct-password', application.bcrypt.gensalt()).decode()
        user = {'user_id': 'u', 'email': 'Legacy@Example.com', 'password_hash': password_hash, 'is_verified': True}
        database = Mock()
        database.users.find_one.side_effect = [None, user]
        with patch.object(application, 'get_db', return_value=database):
            response = self.client.post('/login', json={'email': 'legacy@example.com', 'password': 'correct-password'})
        self.assertEqual(response.status_code, 200)

    def test_password_change_requires_the_current_password(self):
        stored = application.bcrypt.hashpw(b'old-password-123', application.bcrypt.gensalt()).decode()
        database = Mock()
        database.users.find_one.return_value = {'password_hash': stored}
        with patch.object(application, 'get_db', return_value=database):
            wrong = self.client.post('/api/profile/password', headers=self.headers,
                                     json={'current_password': 'nope', 'new_password': 'a-much-longer-password'})
            short = self.client.post('/api/profile/password', headers=self.headers,
                                     json={'current_password': 'old-password-123', 'new_password': 'short'})
            ok = self.client.post('/api/profile/password', headers=self.headers,
                                  json={'current_password': 'old-password-123', 'new_password': 'a-much-longer-password'})
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(short.status_code, 400)
        self.assertEqual(ok.status_code, 200)
        new_hash = database.users.update_one.call_args.args[1]['$set']['password_hash']
        self.assertTrue(application.bcrypt.checkpw(b'a-much-longer-password', new_hash.encode()))
        self.assertEqual(database.users.update_one.call_count, 1)

    def test_investment_revaluation_is_owner_scoped_and_validated(self):
        database = Mock()
        database.investments.update_one.return_value.matched_count = 1
        holding = '64b000000000000000000001'
        with patch.object(application, 'get_db', return_value=database):
            ok = self.client.patch(f'/api/investments/{holding}', headers=self.headers, json={'current_value': 61000})
            negative = self.client.patch(f'/api/investments/{holding}', headers=self.headers, json={'current_value': -1})
            bad_id = self.client.patch('/api/investments/not-an-id', headers=self.headers, json={'current_value': 1})
        self.assertEqual(ok.status_code, 200)
        owner_filter, update = database.investments.update_one.call_args.args
        self.assertEqual(owner_filter['user_id'], 'owner-1')
        self.assertEqual(update['$set']['current_value'], 61000.0)
        self.assertEqual(negative.status_code, 400)
        self.assertEqual(bad_id.status_code, 404)

    def test_login_tokens_expire(self):
        password_hash = application.bcrypt.hashpw(b'correct-password', application.bcrypt.gensalt()).decode()
        database = Mock()
        database.users.find_one.return_value = {'user_id': 'u', 'email': 'a@b.co', 'password_hash': password_hash, 'is_verified': True}
        with patch.object(application, 'get_db', return_value=database):
            token = self.client.post('/login', json={'email': 'a@b.co', 'password': 'correct-password'}).get_json()['token']
        claims = jwt.decode(token, application.SECRET_KEY, algorithms=['HS256'])
        self.assertEqual(claims['exp'] - claims['iat'], application.JWT_TTL_HOURS * 3600)

        expired = jwt.encode({'user_id': 'u', 'exp': 1}, application.SECRET_KEY, algorithm='HS256')
        response = self.client.get('/api/profile', headers={'Authorization': 'Bearer ' + expired})
        self.assertEqual(response.status_code, 401)
        self.assertIn('expired', response.get_json()['error'])

    def test_predict_uses_named_features(self):
        model = Mock()
        model.predict_proba.return_value = [[0.8, 0.2]]
        encoder = Mock()
        encoder.transform.return_value = [3]
        with patch.object(application, 'ml_model', model), patch.object(application, 'encoder', encoder):
            response = self.client.post('/api/predict', headers=self.headers, json={'amount': 100, 'channel': 'UPI', 'account_age': 10})
        self.assertEqual(response.status_code, 200)
        features = model.predict_proba.call_args.args[0]
        self.assertEqual(list(features.columns), application.MODEL_FEATURES)

    def test_profile_image_rejects_non_image_content(self):
        with patch.object(application, 'get_db', return_value=Mock()):
            response = self.client.post('/api/profile/image', headers=self.headers, content_type='multipart/form-data',
                                        data={'image': (io.BytesIO(b'<script>alert(1)</script>'), 'avatar.png')})
        self.assertEqual(response.status_code, 400)

    def test_user_cache_is_invalidated_after_changes(self):
        before = application.user_cache_key('owner-1', 'dashboard_v4', '')
        application.invalidate_user_cache('owner-1')
        self.assertNotEqual(before, application.user_cache_key('owner-1', 'dashboard_v4', ''))

    def test_metrics_history_accumulates_across_retrains_and_is_capped(self):
        sample_metrics = {
            'trained_at': '2026-10-25T00:00:00',
            'random_forest': {'fraud_f1': 0.8, 'fraud_precision': 0.7, 'fraud_recall': 0.9, 'roc_auc': 0.95, 'pr_auc': 0.85},
            'hybrid_risk': {'fraud_f1': 0.81},
            'decision_threshold': 0.5,
            'dataset': {'train': 800, 'test': 200, 'fraud_rate': 0.02},
        }
        with tempfile.TemporaryDirectory() as directory:
            history_path = os.path.join(directory, 'metrics_history.json')
            with patch.object(application, 'METRICS_HISTORY_PATH', history_path):
                application._append_metrics_history(sample_metrics)
                application._append_metrics_history(sample_metrics)

                response = self.client.get('/api/metrics-history', headers=self.headers)
                self.assertEqual(response.status_code, 200)
                history = response.get_json()['history']
                self.assertEqual(len(history), 2)
                self.assertEqual(history[0]['fraud_f1'], 0.8)
                self.assertEqual(history[0]['roc_auc'], 0.95)

                for _ in range(application.METRICS_HISTORY_MAX):
                    application._append_metrics_history(sample_metrics)
                capped = self.client.get('/api/metrics-history', headers=self.headers).get_json()['history']
                self.assertEqual(len(capped), application.METRICS_HISTORY_MAX)

    def test_retraining_the_shared_model_can_be_limited_to_admins(self):
        with patch.object(application, 'ADMIN_EMAILS', {'boss@example.test'}), \
             patch.object(application, 'train_model') as train:
            denied = self.client.post('/api/retrain', headers=self.headers)
            history = self.client.get('/api/metrics-history', headers=self.headers).get_json()
        self.assertEqual(denied.status_code, 403)
        train.assert_not_called()
        self.assertFalse(history['can_retrain'])

        with patch.object(application, 'ADMIN_EMAILS', set()):
            self.assertTrue(self.client.get('/api/metrics-history', headers=self.headers).get_json()['can_retrain'])

    def test_metrics_history_endpoint_returns_empty_before_any_retrain(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(application, 'METRICS_HISTORY_PATH', os.path.join(directory, 'missing.json')):
                response = self.client.get('/api/metrics-history', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['history'], [])


if __name__ == '__main__':
    unittest.main()
