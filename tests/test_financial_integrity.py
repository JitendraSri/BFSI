import contextlib
import io
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt
import pandas as pd
import pymongo
from bson.objectid import ObjectId


with patch.object(pymongo, 'MongoClient'):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app as application


class FinancialIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.user_id = 'financial-test-user'
        self.token = jwt.encode(
            {'user_id': self.user_id, 'email': 'test@example.test'},
            application.SECRET_KEY,
            algorithm='HS256',
        )
        self.db = Mock()
        self.db.users.find_one.return_value = {
            'user_id': self.user_id,
            'balance': 250,
            'kyc_status': 'Pending',
            'trust_score': None,
            'security_status': None,
            'fraud_risk_level': None,
        }

    def auth_headers(self):
        return {'Authorization': 'Bearer ' + self.token}

    def test_dashboard_uses_profile_values_and_withholds_forecast_without_history(self):
        self.db.transactions.count_documents.return_value = 0
        # 5 aggregate calls: chart_data, income_expense, category, fraud_trend, monthly_data (from _compute_user_intelligence)
        self.db.transactions.aggregate.side_effect = [
            [{'_id': '2026-10-01', 'value': 100}],  # chart_data
            [
                {'_id': {'date': '2026-10-01', 'direction': 'credit'}, 'total': 80},
                {'_id': {'date': '2026-10-01', 'direction': 'debit'}, 'total': 30},
            ],  # income_expense
            [{'_id': 'Food', 'total': 30}],  # category_data
            [],  # fraud_trend
            [],  # monthly_data (from _compute_user_intelligence)
        ]
        # Mock find for recent alerts (empty)
        alerts_find_mock = Mock()
        alerts_find_mock.sort.return_value.limit.return_value = []
        # Mock find for fraud_probs in _compute_user_intelligence - returns empty list when list() is called
        fraud_find_mock = Mock()
        fraud_find_mock.__iter__ = Mock(return_value=iter([]))
        # Need to handle two different find calls - one for alerts, one for fraud_probs
        def find_side_effect(*args, **kwargs):
            query = args[0] if args else kwargs.get('filter', {})
            if 'is_fraud' in str(query):
                return alerts_find_mock
            return fraud_find_mock
        self.db.transactions.find.side_effect = find_side_effect
        with patch.object(application, 'get_db', return_value=self.db), \
             patch.object(application.cache, 'get', return_value=None), \
             patch.object(application.cache, 'set'):
            response = self.client.get('/api/dashboard', headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['income_expense_data'][0]['income'], 80)
        self.assertEqual(data['income_expense_data'][0]['expense'], 30)
        self.assertEqual(data['category_data'][0]['category'], 'Food')
        self.assertEqual(data['prediction_data'], [])
        self.assertIsNone(data['intelligence']['expense_prediction'])
        self.assertEqual(data['user_stats']['balance'], 250)
        self.assertEqual(data['user_stats']['trust_score'], 45)
        self.assertEqual(data['user_stats']['security_status'], 'Weak')

    def test_dashboard_calculates_forecast_from_three_completed_debit_months(self):
        current_month = pd.Period(datetime.now(), freq='M')
        debit_rows = [
            {'_id': {'date': f'{(current_month - offset).strftime("%Y-%m")}-12', 'direction': 'debit'}, 'total': amount}
            for offset, amount in ((3, 300), (2, 600), (1, 900))
        ]
        # monthly_data format for _compute_user_intelligence: _id is string like '2026-07'
        monthly_data = [
            {'_id': (current_month - 3).strftime('%Y-%m'), 'total': 300},
            {'_id': (current_month - 2).strftime('%Y-%m'), 'total': 600},
            {'_id': (current_month - 1).strftime('%Y-%m'), 'total': 900},
        ]
        self.db.users.find_one.return_value.update({'is_verified': True, 'trust_score': 62, 'security_status': 'Strong', 'fraud_risk_level': 'Medium'})
        self.db.transactions.count_documents.return_value = 0
        # 5 aggregate calls: chart_data, income_expense, category, fraud_trend, monthly_data (from _compute_user_intelligence)
        self.db.transactions.aggregate.side_effect = [
            [],  # chart_data
            debit_rows + [{'_id': {'date': f'{(current_month - 1).strftime("%Y-%m")}-12', 'direction': 'credit'}, 'total': 2500}],  # income_expense
            [],  # category_data
            [],  # fraud_trend
            monthly_data,  # monthly_data (from _compute_user_intelligence)
        ]
        # Mock find for recent alerts (empty)
        alerts_find_mock = Mock()
        alerts_find_mock.sort.return_value.limit.return_value = []
        # Mock find for fraud_probs in _compute_user_intelligence - returns empty list when list() is called
        fraud_find_mock = Mock()
        fraud_find_mock.__iter__ = Mock(return_value=iter([]))
        # Need to handle two different find calls - one for alerts, one for fraud_probs
        def find_side_effect(*args, **kwargs):
            query = args[0] if args else kwargs.get('filter', {})
            if 'is_fraud' in str(query):
                return alerts_find_mock
            return fraud_find_mock
        self.db.transactions.find.side_effect = find_side_effect
        with patch.object(application, 'get_db', return_value=self.db), \
             patch.object(application.cache, 'get', return_value=None), \
             patch.object(application.cache, 'set'):
            response = self.client.get('/api/dashboard', headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['intelligence']['expense_prediction'], 600)
        self.assertEqual(data['prediction_data'][-1]['predicted'], 600)
        self.assertIsNone(data['prediction_data'][-1]['actual'])
        self.assertEqual(data['user_stats']['trust_score'], 45)
        self.assertEqual(data['user_stats']['security_status'], 'Moderate')
        self.assertEqual(data['user_stats']['fraud_risk_level'], 'Low')

    def test_budget_aggregates_only_current_month_debits_and_uses_saved_limit(self):
        self.db.transactions.aggregate.return_value = [{'_id': 'Food', 'total': 42.5}]
        self.db.transactions.count_documents.return_value = 1
        self.db.users.find_one.return_value = {'budget_limit': 100}
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.get('/api/budget-data', headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        query = self.db.transactions.aggregate.call_args.args[0][0]['$match']
        self.assertEqual(query['direction'], 'debit')
        self.assertIn('timestamp', query)
        self.assertEqual(data['total_spend'], 42.5)
        self.assertEqual(data['budget_limit'], 100)

    def test_credit_score_uses_separate_simulation_field(self):
        self.db.users.find_one.return_value = {'credit_score': 790, 'credit_score_simulation': None}
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.get('/api/credit-score', headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()['score'])
        self.assertEqual(response.get_json()['type'], 'simulation')

        self.db.users.update_one.reset_mock()
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.post(
                '/api/credit-score',
                json={'score': 700},
                headers=self.auth_headers(),
            )
        self.assertEqual(response.status_code, 200)
        update = self.db.users.update_one.call_args.args[1]['$set']
        self.assertIn('credit_score_simulation', update)
        self.assertNotIn('credit_score', update)

    def test_transaction_delete_query_is_scoped_to_owner(self):
        self.db.transactions.find_one.return_value = None
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.delete('/api/transactions/another-users-id', headers=self.auth_headers())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.db.transactions.find_one.call_args.args[0],
            {'transaction_id': 'another-users-id', 'user_id': self.user_id},
        )
        self.db.transactions.delete_one.assert_not_called()

    def test_zero_interest_emi_and_affordability_are_deterministic(self):
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.post(
                '/api/loan/emi',
                json={'loan_amount': 120000, 'annual_interest_rate': 0, 'tenure_years': 2},
                headers=self.auth_headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['monthly_emi'], 5000)
        self.assertEqual(response.get_json()['total_interest'], 0)

        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.post(
                '/api/check-loan-eligibility',
                json={
                    'loan_amount': 120000,
                    'annual_interest_rate': 0,
                    'tenure_years': 2,
                    'monthly_income': 10000,
                },
                headers=self.auth_headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['within_affordability_guideline'])
        self.assertIn('not lender eligibility', response.get_json()['disclaimer'].lower())

    def test_investment_requires_finite_positive_invested_value(self):
        self.db.investments.insert_one.return_value = SimpleNamespace(inserted_id=ObjectId())
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.post(
                '/api/investments',
                json={'type': 'Stocks', 'name': 'Example', 'amount': 1000, 'current_value': 1250},
                headers=self.auth_headers(),
            )
        self.assertEqual(response.status_code, 201)
        saved = self.db.investments.insert_one.call_args.args[0]
        self.assertEqual(saved['user_id'], self.user_id)
        self.assertEqual(saved['valuation_source'], 'user-entered')
        self.assertEqual(saved['current_value'] - saved['amount'], 250)

        with patch.object(application, 'get_db', return_value=self.db):
            invalid = self.client.post(
                '/api/investments',
                json={'type': 'Stocks', 'name': 'Invalid', 'amount': -5, 'current_value': 3},
                headers=self.auth_headers(),
            )
        self.assertEqual(invalid.status_code, 400)

    def test_investment_delete_selector_includes_owner(self):
        investment_id = str(ObjectId())
        self.db.investments.delete_one.return_value.deleted_count = 0
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.post(
                '/api/investments/delete',
                json={'investment_id': investment_id},
                headers=self.auth_headers(),
            )
        self.assertEqual(response.status_code, 404)
        query = self.db.investments.delete_one.call_args.args[0]
        self.assertEqual(query['_id'], ObjectId(investment_id))
        self.assertEqual(query['user_id'], self.user_id)


if __name__ == '__main__':
    unittest.main()