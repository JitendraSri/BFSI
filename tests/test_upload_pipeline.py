import contextlib
import io
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import jwt
import numpy as np
import pandas as pd
import pymongo


with patch.object(pymongo, 'MongoClient'):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app as application


class _Users:
    def find_one(self, query, projection=None):
        return {
            'user_id': 'owner-1',
            'kyc_status': 'Verified',
            'created_at': datetime(2020, 1, 1),
        }


class _Transactions:
    def bulk_write(self, operations):
        self.operations = operations
        return SimpleNamespace(upserted_count=len(operations), modified_count=0, matched_count=0)


class _Database:
    users = _Users()
    transactions = _Transactions()
    file_uploads = Mock()


class UploadPipelineTests(unittest.TestCase):
    def test_maps_ledger_headers_and_preserves_unknown_direction(self):
        frame = pd.DataFrame([
            {'action': 'completed', 'amount': '1,250.50', 'channel': 'card',
             'date': '2026-10-09', 'id': 'TX-1', 'status': 'settled'},
            {'action': 'debit', 'amount': '-20.00', 'channel': 'cash',
             'date': '2026-10-10', 'id': 'TX-2', 'status': 'completed'},
        ])
        normalized = application.normalize_uploaded_transactions(
            frame, 'owner-1', {'kyc_status': 'Verified', 'created_at': datetime(2020, 1, 1)}
        )
        self.assertEqual(normalized.loc[0, 'transaction_amount'], 1250.5)
        self.assertEqual(normalized.loc[0, 'direction'], 'unknown')
        self.assertEqual(normalized.loc[1, 'transaction_amount'], 20.0)
        self.assertEqual(normalized.loc[1, 'direction'], 'debit')
        self.assertTrue((normalized['customer_id'] == 'owner-1').all())
        self.assertTrue((normalized['kyc_verified'] == 1).all())
        self.assertEqual(normalized.loc[0, 'status'], 'settled')

    def test_missing_model_does_not_label_records_safe(self):
        frame = pd.DataFrame([{'amount': 50, 'channel': 'unknown'}])
        with patch.object(application, 'ml_model', None), patch.object(application, 'encoder', None):
            normalized = application.normalize_uploaded_transactions(frame, 'owner-1')
        self.assertTrue(pd.isna(normalized.loc[0, 'is_fraud']))
        self.assertTrue(pd.isna(normalized.loc[0, 'fraud_probability']))
        self.assertTrue(pd.isna(normalized.loc[0, 'timestamp']))

    def test_bank_statement_layout_keeps_direction_amounts_and_day_first_dates(self):
        statement = pd.DataFrame({
            'Date': ['01/09/26', '05/09/26', '06/09/26'],
            'Narration': ['NEFT-ACME-SALARY', 'IMPS-RENT', 'BALANCE B/F'],
            'Chq./Ref.No.': ['R1', 'R2', 'R3'],
            'Withdrawal Amt.': ['', '22,000.00', ''],
            'Deposit Amt.': ['85,000.00', '', ''],
            'Closing Balance': ['1,85,000.00', '1,63,000.00', '1,63,000.00'],
        })
        normalized, invalid = application.normalize_uploaded_transactions(statement, 'owner-1', {}, return_invalid=True)
        self.assertEqual(list(normalized['transaction_id']), ['R1', 'R2'])
        self.assertEqual(list(normalized['direction']), ['credit', 'debit'])
        self.assertEqual(list(normalized['transaction_amount']), [85000.0, 22000.0])
        self.assertEqual(normalized.loc[0, 'description'], 'NEFT-ACME-SALARY')
        self.assertEqual(normalized.loc[0, 'timestamp'], datetime(2026, 9, 1))
        self.assertEqual(len(invalid), 1)  # the row with neither a withdrawal nor a deposit

    def test_missing_currency_defaults_to_account_currency(self):
        no_column = application.normalize_uploaded_transactions(pd.DataFrame([{'amount': 25}]), 'owner-1')
        self.assertEqual(no_column.loc[0, 'currency'], 'INR')

        mixed = pd.DataFrame([{'amount': 25, 'currency': 'USD'}, {'amount': 30, 'currency': None}, {'amount': 5, 'currency': ' '}])
        normalized = application.normalize_uploaded_transactions(mixed, 'owner-1', {'currency': 'eur'})
        self.assertEqual(list(normalized['currency']), ['USD', 'EUR', 'EUR'])

    def test_numeric_kyc_flags_are_normalized(self):
        frame = pd.DataFrame([{'amount': 25, 'kyc_verified': 1.0}])
        normalized = application.normalize_uploaded_transactions(frame, 'owner-1')
        self.assertEqual(normalized.loc[0, 'kyc_verified'], 1)

    def test_authenticated_upload_persists_analyzed_owned_transaction(self):
        database = _Database()
        staged_previews = {}
        def cache_set(key, value, timeout=None):
            staged_previews[key] = value
        def cache_get(key):
            return staged_previews.get(key)
        def cache_delete(key):
            staged_previews.pop(key, None)

        token = jwt.encode(
            {'user_id': 'owner-1', 'email': 'owner@example.test'},
            application.SECRET_KEY,
            algorithm='HS256',
        )
        payload = b'action,amount,channel,date,id,status\ndebit,"1,250.50",card,2026-10-09,TX-1,completed\n'
        with patch.object(application, 'get_db', return_value=database), \
               patch.object(application.cache, 'set', side_effect=cache_set), \
               patch.object(application.cache, 'get', side_effect=cache_get), \
               patch.object(application.cache, 'delete', side_effect=cache_delete), \
             patch.object(application, 'ml_model') as model, \
             patch.object(application, 'encoder') as encoder:
            model.predict_proba.return_value = np.array([[0.1, 0.9]])
            encoder.transform.return_value = [1]
            response = application.app.test_client().post(
                '/upload',
                data={'file': (io.BytesIO(payload), 'ledger.csv')},
                headers={'Authorization': 'Bearer ' + token},
                content_type='multipart/form-data',
            )

        self.assertEqual(response.status_code, 200, response.get_json())
        preview = response.get_json()
        self.assertEqual(preview['status'], 'preview')
        self.assertEqual(preview['preview'][0]['transaction_id'], 'TX-1')
        self.assertFalse(hasattr(database.transactions, 'operations'))

        with patch.object(application, 'get_db', return_value=database), \
             patch.object(application.cache, 'get', side_effect=cache_get), \
             patch.object(application.cache, 'delete', side_effect=cache_delete):
            confirmed = application.app.test_client().post(
                '/upload/confirm',
                json={'preview_id': preview['preview_id']},
                headers={'Authorization': 'Bearer ' + token},
            )
        self.assertEqual(confirmed.status_code, 201, confirmed.get_json())
        operation = database.transactions.operations[0]
        document = operation._doc['$set']
        self.assertEqual(operation._filter, {'transaction_id': 'TX-1', 'user_id': 'owner-1'})
        self.assertEqual(document['transaction_amount'], 1250.5)
        self.assertEqual(document['direction'], 'debit')
        self.assertEqual(document['is_fraud'], 1)
        self.assertEqual(document['fraud_probability'], 0.9)
        self.assertEqual(document['source_file'], 'ledger.csv')
        self.assertEqual(document['source_row'], 2)
        self.assertIn('import_batch_id', document)

        foreign_preview_id = 'f' * 32
        staged_previews[f'upload_preview:owner-1:{foreign_preview_id}'] = {
            'rows': '[]',
            'file_name': 'private.csv',
            'import_batch_id': 'batch',
            'rows_detected': 0,
            'rejected_rows': 0,
            'duplicate_rows': 0,
            'explanation': '',
            'risk_percentage': 0,
        }
        other_token = jwt.encode(
            {'user_id': 'owner-2', 'email': 'other@example.test'},
            application.SECRET_KEY,
            algorithm='HS256',
        )
        with patch.object(application, 'get_db', return_value=database), \
             patch.object(application.cache, 'get', side_effect=cache_get):
            forbidden = application.app.test_client().post(
                '/upload/confirm',
                json={'preview_id': foreign_preview_id},
                headers={'Authorization': 'Bearer ' + other_token},
            )
        self.assertEqual(forbidden.status_code, 410)
        self.assertEqual(len(database.transactions.operations), 1)

    def test_high_risk_import_triggers_fraud_alert_email(self):
        df = pd.DataFrame([{
            'transaction_id': 'TXN-1', 'customer_id': 'owner-1', 'kyc_verified': 0, 'account_age_days': 1,
            'transaction_amount': 99999.0, 'channel': 'ATM', 'timestamp': pd.NaT, 'direction': 'debit',
            'category': 'Uncategorized', 'currency': 'INR', 'description': None, 'is_fraud': 1,
            'fraud_probability': 0.95, 'anomaly_score': 0.9, 'risk_score': 92.0, 'risk_level': 'High',
            'risk_reasons': ['Fraud model score 95% is above the 50% alert threshold'], '_source_row': 2,
        }])
        database = Mock()
        database.transactions.bulk_write.return_value = SimpleNamespace(upserted_count=1, modified_count=0, matched_count=0)
        database.users.find_one.return_value = {'email': 'owner@example.test'}

        with patch.object(application, 'get_db', return_value=database), \
             patch.object(application, 'send_fraud_alert_email', return_value=True) as alert, \
             patch.object(application, 'invalidate_user_cache'):
            application.persist_transaction_import(df, 'owner-1', 'ledger.csv', 'batch-1', 1, 0, 0)

        alert.assert_called_once()
        email, rows, file_name = alert.call_args.args
        self.assertEqual(email, 'owner@example.test')
        self.assertEqual(rows[0]['transaction_id'], 'TXN-1')
        self.assertEqual(file_name, 'ledger.csv')

    def test_low_risk_import_does_not_send_fraud_alert_email(self):
        df = pd.DataFrame([{
            'transaction_id': 'TXN-2', 'customer_id': 'owner-1', 'kyc_verified': 1, 'account_age_days': 400,
            'transaction_amount': 50.0, 'channel': 'UPI', 'timestamp': pd.NaT, 'direction': 'debit',
            'category': 'Uncategorized', 'currency': 'INR', 'description': None, 'is_fraud': 0,
            'fraud_probability': 0.01, 'anomaly_score': 0.01, 'risk_score': 2.0, 'risk_level': 'Low',
            'risk_reasons': [], '_source_row': 2,
        }])
        database = Mock()
        database.transactions.bulk_write.return_value = SimpleNamespace(upserted_count=1, modified_count=0, matched_count=0)

        with patch.object(application, 'get_db', return_value=database), \
             patch.object(application, 'send_fraud_alert_email', return_value=True) as alert, \
             patch.object(application, 'invalidate_user_cache'):
            application.persist_transaction_import(df, 'owner-1', 'ledger.csv', 'batch-1', 1, 0, 0)

        alert.assert_not_called()


if __name__ == '__main__':
    unittest.main()