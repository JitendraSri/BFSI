import contextlib
import io
import unittest
from datetime import datetime
from types import SimpleNamespace
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
        return {'user_id': 'owner-1', 'kyc_status': 'Verified', 'created_at': datetime(2020, 1, 1)}


class _Transactions:
    def bulk_write(self, operations):
        self.operations = operations
        return SimpleNamespace(upserted_count=len(operations), modified_count=0, matched_count=0)

    def delete_many(self, query):
        return SimpleNamespace(deleted_count=1)


class _Database:
    users = _Users()
    transactions = _Transactions()
    file_uploads = Mock()


class UploadImportFeaturesTests(unittest.TestCase):
    def test_column_mapping_and_invalid_rows_export(self):
        database = _Database()
        token = jwt.encode({'user_id': 'owner-1', 'email': 'owner@example.test'}, application.SECRET_KEY, algorithm='HS256')
        frame = pd.DataFrame([
            {'reference': 'A-1', 'net_amount': '100.00', 'date': '2026-10-01', 'channel': 'UPI', 'merchant': 'Grocer', 'status': 'posted'},
            {'reference': 'A-2', 'net_amount': '', 'date': '2026-10-02', 'channel': 'Card', 'merchant': 'Cafe', 'status': 'posted'},
        ])
        staged = {
            'rows': frame.to_json(orient='records', date_format='iso'),
            'file_name': 'sample.csv',
            'import_batch_id': 'batch-123',
            'rows_detected': 2,
            'rejected_rows': 0,
            'duplicate_rows': 0,
            'duplicate_review': [],
            'invalid_rows_csv': '',
            'explanation': '',
            'risk_percentage': 0,
        }
        staged_key = f"upload_preview:owner-1:{'a' * 32}"
        with patch.object(application, 'get_db', return_value=database), patch.object(application.cache, 'get', side_effect=lambda key: staged if key == staged_key else None), patch.object(application.cache, 'set', side_effect=lambda key, value, timeout=None: staged.update(value) if key == staged_key else None), patch.object(application.cache, 'delete'):
            response = application.app.test_client().post(
                '/upload/map',
                json={'preview_id': 'a' * 32, 'column_map': {'reference': 'transaction_id', 'net_amount': 'transaction_amount', 'merchant': 'description', 'date': 'timestamp'}},
                headers={'Authorization': 'Bearer ' + token},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            payload = response.get_json()
            self.assertIn('transaction_id', payload['preview'][0])
            self.assertEqual(payload['preview'][0]['transaction_amount'], 100.0)

            invalid_csv = application.app.test_client().get(
                '/upload/invalid-csv?preview_id=' + ('a' * 32),
                headers={'Authorization': 'Bearer ' + token},
            )
        self.assertEqual(invalid_csv.status_code, 200)
        self.assertIn('reference', invalid_csv.get_data(as_text=True))

    def test_duplicate_review_and_rollback(self):
        database = _Database()
        token = jwt.encode({'user_id': 'owner-1', 'email': 'owner@example.test'}, application.SECRET_KEY, algorithm='HS256')
        frame = pd.DataFrame([
            {'transaction_id': 'DUP-1', 'amount': 100, 'direction': 'debit', 'channel': 'UPI', 'description': 'A', 'status': 'posted', 'date': '2026-10-01'},
            {'transaction_id': 'DUP-1', 'amount': 115, 'direction': 'debit', 'channel': 'UPI', 'description': 'B', 'status': 'posted', 'date': '2026-10-01'},
        ])
        normalized = application.normalize_uploaded_transactions(frame, 'owner-1', {'kyc_status': 'Verified', 'created_at': datetime(2020, 1, 1)})
        duplicate_review = []
        groups = normalized[normalized.duplicated(subset=['transaction_id'], keep=False)].groupby('transaction_id', dropna=False)
        for transaction_id, group in groups:
            duplicate_review.append({'transaction_id': str(transaction_id), 'rows': [int(row + 2) for row in group.index.tolist()]})
        self.assertEqual(len(duplicate_review), 1)
        self.assertEqual(duplicate_review[0]['transaction_id'], 'DUP-1')

        with patch.object(application, 'get_db', return_value=database), patch.object(application.cache, 'get', return_value={'rows': normalized.to_json(orient='records', date_format='iso'), 'file_name': 'dup.csv', 'import_batch_id': 'batch-dup', 'rows_detected': 2, 'rejected_rows': 0, 'duplicate_rows': 1, 'duplicate_review': duplicate_review, 'invalid_rows_csv': '', 'explanation': '', 'risk_percentage': 0}), patch.object(application.cache, 'delete'):
            confirmed = application.app.test_client().post('/upload/confirm', json={'preview_id': 'a' * 32}, headers={'Authorization': 'Bearer ' + token})
            self.assertEqual(confirmed.status_code, 201)
            rollback = application.app.test_client().post('/upload/rollback', json={'import_batch_id': 'batch-dup'}, headers={'Authorization': 'Bearer ' + token})
            self.assertEqual(rollback.status_code, 200)
            self.assertEqual(rollback.get_json()['deleted_count'], 1)


if __name__ == '__main__':
    unittest.main()
