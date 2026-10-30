import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt
import pandas as pd
import pymongo
from bson.objectid import ObjectId
from PIL import Image as PillowImage


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
        self.db.transactions.distinct.return_value = ['INR']
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

    def test_transactions_page_serves_ledger_assets(self):
        response = self.client.get('/transactions.html')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('Transaction History', page)
        self.assertIn('/static/css/transactions.css', page)
        # Ledger logic is inlined into the page (loadTxns / exportCSV), not a separate JS file.
        self.assertIn('async function loadTxns', page)
        self.assertIn('function exportCSV', page)
        self.assertEqual(self.client.get('/static/css/transactions.css').status_code, 200)

    def test_budget_page_is_removed_but_budget_api_remains_available(self):
        for path in ('/budget', '/budget.html'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

        navbar_path = os.path.join(application.app.root_path, 'static', 'js', 'navbar.js')
        with open(navbar_path, encoding='utf-8') as navbar_file:
            self.assertNotIn('budget.html', navbar_file.read())

        self.db.transactions.aggregate.return_value = []
        self.db.transactions.count_documents.return_value = 0
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.get('/api/budget-data', headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)

    def test_rag_page_identifies_gemini_as_answer_generator(self):
        response = self.client.get('/rag')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('FinRAG <span>Copilot</span>', page)
        self.assertIn('General chat with Gemini', page)

    def test_rag_api_accepts_general_chat_without_a_selected_document(self):
        answer = {
            'mode': 'conversation',
            'answer': 'Hi! How can I help you today?',
            'sources': [],
        }
        with patch.object(application, 'ask_document', return_value=answer) as ask, \
             patch.dict(os.environ, {'GEMINI_API_KEY': 'test-api-key'}):
            response = self.client.post(
                '/api/rag/ask',
                json={'query': 'Hi', 'document_id': '', 'history': []},
                headers=self.auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['mode'], 'conversation')
        self.assertEqual(ask.call_args.args[:3], (self.user_id, '', 'Hi'))
        self.assertEqual(ask.call_args.kwargs['chat_history'], [])

    def test_profile_returns_email_verification_and_separate_savings(self):
        self.db.users.find_one.return_value.update({
            'user_id': self.user_id,
            'is_verified': True,
            'savings_amount': 8200.5,
            'budget_limit': 40000.0,
            'trust_score': 85,
        })
        self.db.transactions.count_documents.return_value = 0
        self.db.transactions.find.return_value = []
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.get('/api/profile', headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        profile = response.get_json()
        self.assertTrue(profile['email_verified'])
        self.assertEqual(profile['savings_amount'], 8200.5)
        self.assertEqual(profile['budget_limit'], 40000.0)
        self.assertNotIn('kyc_status', profile)
        # Computed live like the dashboard; the stale stored 85 is ignored.
        self.assertEqual(profile['trust_score'], 49)
        self.assertEqual(profile['security_status'], 'Strong')

    def test_profile_saves_budget_and_currency_settings_and_validates_them(self):
        self.db.users.find_one.return_value = {'user_id': self.user_id, 'email': 'test@example.test', 'currency': 'INR'}
        self.db.users.update_one.return_value.matched_count = 1
        with patch.object(application, 'get_db', return_value=self.db):
            saved = self.client.put('/api/profile', json={'budget_limit': '45000', 'currency': 'usd'}, headers=self.auth_headers())
            bad_budget = self.client.put('/api/profile', json={'budget_limit': -5}, headers=self.auth_headers())
            bad_currency = self.client.put('/api/profile', json={'currency': 'rupees'}, headers=self.auth_headers())
            cleared = self.client.put('/api/profile', json={'budget_limit': ''}, headers=self.auth_headers())
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(bad_budget.status_code, 400)
        self.assertEqual(bad_currency.status_code, 400)
        self.assertEqual(cleared.status_code, 200)
        first_update = self.db.users.update_one.call_args_list[0].args[1]['$set']
        self.assertEqual(first_update, {'budget_limit': 45000.0, 'currency': 'USD'})
        self.assertIsNone(self.db.users.update_one.call_args_list[-1].args[1]['$set']['budget_limit'])

    def test_savings_update_does_not_change_account_balance(self):
        profile = {
            'user_id': self.user_id,
            'name': 'Test User',
            'email': 'test@example.test',
            'balance': 250,
            'currency': 'INR',
            'is_verified': True,
            'kyc_status': 'Pending',
        }
        self.db.users.find_one.return_value = profile
        self.db.users.update_one.return_value.matched_count = 1
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.put(
                '/api/profile',
                json={'savings_amount': 9250.75},
                headers=self.auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        update = self.db.users.update_one.call_args.args[1]['$set']
        self.assertEqual(update['savings_amount'], 9250.75)
        self.assertEqual(update['savings_currency'], 'INR')
        self.assertNotIn('balance', update)

    def test_changing_profile_email_requires_new_verification(self):
        updated_user = {
            'user_id': self.user_id,
            'name': 'Test User',
            'email': 'new@example.test',
            'is_verified': False,
            'savings_amount': None,
        }
        self.db.users.find_one.side_effect = [
            {'user_id': self.user_id, 'email': 'test@example.test', 'is_verified': True},
            None,
            updated_user,
        ]
        self.db.users.update_one.return_value.matched_count = 1
        with patch.object(application, 'get_db', return_value=self.db), \
             patch.object(application, 'send_otp_email', return_value=True) as send_email:
            response = self.client.put(
                '/api/profile',
                json={'name': 'Test User', 'email': 'NEW@example.test'},
                headers=self.auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        update = self.db.users.update_one.call_args.args[1]['$set']
        self.assertFalse(update['is_verified'])
        self.assertIn('otp_hash', update)
        self.assertTrue(response.get_json()['email_verification_required'])
        self.assertFalse(response.get_json()['email_verified'])
        send_email.assert_called_once()

    def test_dashboard_page_serves_financial_intelligence_assets(self):
        response = self.client.get('/dashboard')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('Welcome back', page)
        self.assertIn('txnVolumeChart', page)
        self.assertEqual(self.client.get('/static/css/dashboard.css').status_code, 200)
        self.assertEqual(self.client.get('/static/js/dashboard.js').status_code, 200)

    def _dashboard_cursors(self):
        alerts_cursor = Mock()
        alerts_cursor.sort.return_value.limit.return_value = []
        empty_cursor = Mock()
        empty_cursor.__iter__ = Mock(return_value=iter([]))
        empty_cursor.sort.return_value = []  # subscription detector: find(...).sort(...) iterated directly
        self.db.transactions.find.side_effect = lambda query, *args, **kwargs: (
            alerts_cursor if query.get('is_fraud') == 1 else empty_cursor
        )

    def _get_dashboard(self, query=''):
        with patch.object(application, 'get_db', return_value=self.db),              patch.object(application.cache, 'get', return_value=None),              patch.object(application.cache, 'set'):
            return self.client.get('/api/dashboard' + query, headers=self.auth_headers())

    def test_dashboard_opens_on_dominant_currency_and_never_mixes_currencies(self):
        self.db.transactions.distinct.return_value = ['INR', 'USD']
        counts = {'USD': 50, 'INR': 10}

        def count_documents(query, *args, **kwargs):
            values = (query.get('currency') or {}).get('$in', []) if isinstance(query.get('currency'), dict) else []
            return next((counts[code] for code in counts if code in values), 0)
        self.db.transactions.count_documents.side_effect = count_documents
        self.db.transactions.aggregate.return_value = []
        self._dashboard_cursors()

        unscoped = self._get_dashboard()
        self.assertEqual(unscoped.status_code, 200)
        self.assertEqual(unscoped.get_json()['selected_currency'], 'USD')
        self.assertEqual(unscoped.get_json()['available_currencies'], ['INR', 'USD'])
        self.assertEqual(self.db.transactions.aggregate.call_args_list[0].args[0][0]['$match']['currency'], {'$in': ['USD']})

        self.db.transactions.aggregate.reset_mock()
        scoped = self._get_dashboard('?currency=INR')
        self.assertEqual(scoped.get_json()['selected_currency'], 'INR')
        self.assertEqual(self.db.transactions.aggregate.call_args_list[0].args[0][0]['$match']['currency'],
                         {'$in': ['INR', None, '']})

        self.assertEqual(self._get_dashboard('?currency=EUR').status_code, 400)

    def test_dashboard_treats_untagged_records_as_account_currency(self):
        self.db.transactions.distinct.return_value = [None]
        self.db.transactions.count_documents.side_effect = lambda query, *args, **kwargs: (
            1 if query.get('currency') == {'$in': [None, '']} else 0)
        self.db.transactions.aggregate.return_value = []
        self._dashboard_cursors()

        response = self._get_dashboard()
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['selected_currency'], 'INR')
        self.assertTrue(body['untagged_currency_assumed'])
        self.assertEqual(self.db.transactions.aggregate.call_args_list[0].args[0][0]['$match']['currency'], {'$in': [None, '']})

    def test_dashboard_uses_profile_values_and_withholds_forecast_without_history(self):
        self.db.users.find_one.return_value.update({'savings_amount': 8200.5, 'savings_currency': 'INR'})
        self.db.transactions.count_documents.return_value = 0
        # 6 aggregate calls: chart_data, income_expense, category, month-over-month spend insight,
        # fraud_trend, monthly_data (from _compute_user_intelligence)
        self.db.transactions.aggregate.side_effect = [
            [{'_id': '2026-10-01', 'value': 100}],  # chart_data
            [
                {'_id': {'date': '2026-10-01', 'direction': 'credit'}, 'total': 80},
                {'_id': {'date': '2026-10-01', 'direction': 'debit'}, 'total': 30},
            ],  # income_expense
            [{'_id': 'Food', 'total': 30}],  # category_data
            [],  # month-over-month spend insight
            [],  # fraud_trend
            [],  # monthly_data (from _compute_user_intelligence)
        ]
        # Mock find for recent alerts (empty)
        alerts_find_mock = Mock()
        alerts_find_mock.sort.return_value.limit.return_value = []
        # Mock find for fraud_probs in _compute_user_intelligence - returns empty list when list() is called
        fraud_find_mock = Mock()
        fraud_find_mock.__iter__ = Mock(return_value=iter([]))
        # Mock find for the subscription detector: find(...).sort(...) iterated directly
        subs_find_mock = Mock()
        subs_find_mock.sort.return_value = []
        # Need to handle three different find calls: alerts, fraud_probs, and recurring-payment detection
        def find_side_effect(*args, **kwargs):
            query = args[0] if args else kwargs.get('filter', {})
            if 'is_fraud' in str(query):
                return alerts_find_mock
            if 'direction' in query:
                return subs_find_mock
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
        self.assertEqual(data['user_stats']['savings_amount'], 8200.5)
        self.assertEqual(data['user_stats']['savings_currency'], 'INR')
        self.assertEqual(data['user_stats']['trust_score'], 49)
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
        # 6 aggregate calls: chart_data, income_expense, category, month-over-month spend insight,
        # fraud_trend, monthly_data (from _compute_user_intelligence)
        self.db.transactions.aggregate.side_effect = [
            [],  # chart_data
            debit_rows + [{'_id': {'date': f'{(current_month - 1).strftime("%Y-%m")}-12', 'direction': 'credit'}, 'total': 2500}],  # income_expense
            [],  # category_data
            [],  # month-over-month spend insight
            [],  # fraud_trend
            monthly_data,  # monthly_data (from _compute_user_intelligence)
        ]
        # Mock find for recent alerts (empty)
        alerts_find_mock = Mock()
        alerts_find_mock.sort.return_value.limit.return_value = []
        # Mock find for fraud_probs in _compute_user_intelligence - returns empty list when list() is called
        fraud_find_mock = Mock()
        fraud_find_mock.__iter__ = Mock(return_value=iter([]))
        # Mock find for the subscription detector: find(...).sort(...) iterated directly
        subs_find_mock = Mock()
        subs_find_mock.sort.return_value = []
        # Need to handle three different find calls: alerts, fraud_probs, and recurring-payment detection
        def find_side_effect(*args, **kwargs):
            query = args[0] if args else kwargs.get('filter', {})
            if 'is_fraud' in str(query):
                return alerts_find_mock
            if 'direction' in query:
                return subs_find_mock
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
        self.assertEqual(data['user_stats']['trust_score'], 49)
        self.assertEqual(data['user_stats']['security_status'], 'Strong')
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
        self.db.transactions.count_documents.return_value = 0
        self.db.transactions.aggregate.return_value = []
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.get('/api/credit-score', headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        # No saved simulation yet: the baseline is computed from the account's own data, not a flat default.
        self.assertEqual(body['score'], body['base_score'])
        self.assertTrue(300 <= body['base_score'] <= 850)
        self.assertEqual(body['type'], 'simulation')

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

    def test_transaction_query_filters_in_the_database(self):
        query = application._transaction_query(self.user_id, {'status': 'disputed', 'q': 'swiggy.*', 'start_date': '2026-10-01'})
        self.assertEqual(query['user_id'], self.user_id)
        self.assertTrue(query['disputed'])
        self.assertEqual(query['timestamp']['$gte'], datetime(2026, 10, 1))
        # User text is matched literally, never as a regular expression.
        self.assertIn({'description': {'$regex': 'swiggy\\.\\*', '$options': 'i'}}, query['$or'])

        amount_query = application._transaction_query(self.user_id, {'q': '1,250.50'})
        self.assertIn({'transaction_amount': 1250.5}, amount_query['$or'])
        with self.assertRaises(ValueError):
            application._transaction_query(self.user_id, {'status': 'everything'})

    def test_transactions_endpoint_pages_and_summarises_all_matching_records(self):
        self.db.transactions.aggregate.return_value = [{'_id': None, 'total': 120, 'flagged': 3, 'disputed': 1,
                                                        'credits': 10, 'debits': 110, 'latest': datetime(2026, 10, 20)}]
        cursor = Mock()
        cursor.sort.return_value.skip.return_value.limit.return_value = [{'_id': 'x1', 'transaction_id': 'T-51'}]
        self.db.transactions.find.return_value = cursor
        with patch.object(application, 'get_db', return_value=self.db), \
             patch.object(application.cache, 'get', return_value=None), patch.object(application.cache, 'set'):
            response = self.client.get('/api/transactions?page=2&page_size=50&status=flagged', headers=self.auth_headers())
            bad = self.client.get('/api/transactions?status=nope', headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['total'], 120)
        self.assertEqual(body['summary']['flagged'], 3)
        self.assertEqual(body['items'][0]['transaction_id'], 'T-51')
        cursor.sort.return_value.skip.assert_called_once_with(50)
        self.assertEqual(self.db.transactions.find.call_args.args[0]['is_fraud'], 1)
        self.assertEqual(bad.status_code, 400)

    def test_statement_export_is_owner_scoped_and_neutralises_formulas(self):
        cursor = Mock()
        cursor.sort.return_value.limit.return_value = [
            {'transaction_id': 'T-1', 'description': '=HYPERLINK("evil")', 'transaction_amount': -42.5, 'disputed': True},
        ]
        self.db.transactions.find.return_value = cursor
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.get('/api/transactions/export?status=disputed', headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)
        csv_text = response.get_data(as_text=True)
        self.assertIn('transaction_id,timestamp', csv_text)
        self.assertIn('"\'=HYPERLINK(""evil"")"', csv_text)
        self.assertIn('"-42.5"', csv_text)
        self.assertEqual(self.db.transactions.find.call_args.args[0]['user_id'], self.user_id)

    def test_alert_review_records_owner_verdict_as_a_training_label(self):
        self.db.transactions.find_one.return_value = None
        with patch.object(application, 'get_db', return_value=self.db):
            missing = self.client.post('/api/alerts/other/review', json={'verdict': 'fraud'}, headers=self.auth_headers())
            bad = self.client.post('/api/alerts/T-1/review', json={'verdict': 'maybe'}, headers=self.auth_headers())
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(bad.status_code, 400)
        self.db.transactions.update_one.assert_not_called()

        self.db.transactions.find_one.return_value = {'_id': 1}
        with patch.object(application, 'get_db', return_value=self.db):
            legit = self.client.post('/api/alerts/T-1/review', json={'verdict': 'legitimate'}, headers=self.auth_headers())
        self.assertEqual(legit.status_code, 200)
        owner_filter, update = self.db.transactions.update_one.call_args.args
        self.assertEqual(owner_filter, {'transaction_id': 'T-1', 'user_id': self.user_id})
        self.assertEqual(update['$set']['is_fraud'], 0)
        self.assertEqual(update['$set']['review_status'], 'legitimate')
        self.assertEqual(update['$set']['label_source'], 'user_review')

        with patch.object(application, 'get_db', return_value=self.db):
            self.client.post('/api/alerts/T-1/review', json={'verdict': 'reopen'}, headers=self.auth_headers())
        update = self.db.transactions.update_one.call_args.args[1]
        self.assertEqual(update['$set'], {'is_fraud': 1})
        self.assertIn('review_status', update['$unset'])

    def test_transaction_dispute_toggle_is_scoped_to_owner_and_flips_state(self):
        self.db.transactions.find_one.return_value = None
        with patch.object(application, 'get_db', return_value=self.db):
            missing = self.client.post('/api/transactions/another-users-id/dispute', headers=self.auth_headers())
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            self.db.transactions.find_one.call_args.args[0],
            {'transaction_id': 'another-users-id', 'user_id': self.user_id},
        )
        self.db.transactions.update_one.assert_not_called()

        self.db.transactions.find_one.return_value = {'transaction_id': 'TXN-9', 'user_id': self.user_id, 'disputed': False}
        with patch.object(application, 'get_db', return_value=self.db):
            toggled = self.client.post('/api/transactions/TXN-9/dispute', headers=self.auth_headers())
        self.assertEqual(toggled.status_code, 200)
        self.assertTrue(toggled.get_json()['disputed'])
        update_filter, update_doc = self.db.transactions.update_one.call_args.args
        self.assertEqual(update_filter, {'transaction_id': 'TXN-9', 'user_id': self.user_id})
        self.assertTrue(update_doc['$set']['disputed'])
        self.assertIsNotNone(update_doc['$set']['disputed_at'])

        self.db.transactions.find_one.return_value = {'transaction_id': 'TXN-9', 'user_id': self.user_id, 'disputed': False}
        with patch.object(application, 'get_db', return_value=self.db):
            explicit = self.client.post('/api/transactions/TXN-9/dispute', json={'disputed': False}, headers=self.auth_headers())
        self.assertEqual(explicit.status_code, 200)
        self.assertFalse(explicit.get_json()['disputed'])

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

    def test_loan_amortization_schedule_and_prepayment_savings(self):
        with patch.object(application, 'get_db', return_value=self.db):
            baseline = self.client.post(
                '/api/loan/amortization',
                json={'loan_amount': 120000, 'annual_interest_rate': 12, 'tenure_years': 2},
                headers=self.auth_headers(),
            )
        self.assertEqual(baseline.status_code, 200)
        base_data = baseline.get_json()
        self.assertEqual(base_data['months'], 24)
        self.assertEqual(base_data['months_saved'], 0)
        self.assertGreater(base_data['total_interest'], 0)
        total_principal_paid = sum(y['principal_paid'] for y in base_data['schedule_yearly'])
        self.assertAlmostEqual(total_principal_paid, 120000, delta=1)

        with patch.object(application, 'get_db', return_value=self.db):
            prepaid = self.client.post(
                '/api/loan/amortization',
                json={'loan_amount': 120000, 'annual_interest_rate': 12, 'tenure_years': 2, 'extra_monthly_payment': 2000},
                headers=self.auth_headers(),
            )
        self.assertEqual(prepaid.status_code, 200)
        prepaid_data = prepaid.get_json()
        self.assertLess(prepaid_data['months'], base_data['months'])
        self.assertGreater(prepaid_data['months_saved'], 0)
        self.assertGreater(prepaid_data['interest_saved'], 0)

    def test_loan_amortization_rejects_negative_prepayment(self):
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.post(
                '/api/loan/amortization',
                json={'loan_amount': 120000, 'annual_interest_rate': 12, 'tenure_years': 2, 'extra_monthly_payment': -500},
                headers=self.auth_headers(),
            )
        self.assertEqual(response.status_code, 400)

    def test_financial_health_score_rewards_good_behaviour_over_bad(self):
        good_user = {'created_at': datetime.now() - timedelta(days=400),
                     'balance': 500000, 'budget_limit': 10000}
        bad_user = {'created_at': datetime.now() - timedelta(days=5),
                    'balance': 100, 'budget_limit': 10000}

        good_db = Mock()
        good_db.transactions.count_documents.side_effect = [100, 0]
        good_db.transactions.aggregate.return_value = [{'total': 5000}]

        bad_db = Mock()
        bad_db.transactions.count_documents.side_effect = [100, 40]
        bad_db.transactions.aggregate.return_value = [{'total': 50000}]

        good_score = application._compute_financial_health_score(good_db, 'u1', good_user)
        bad_score = application._compute_financial_health_score(bad_db, 'u2', bad_user)

        self.assertGreater(good_score, bad_score)
        self.assertTrue(300 <= good_score <= 850)
        self.assertTrue(300 <= bad_score <= 850)

    def test_credit_score_get_uses_computed_baseline_once_saved(self):
        self.db.users.find_one.return_value = {'credit_score_simulation': 720}
        self.db.transactions.count_documents.return_value = 0
        self.db.transactions.aggregate.return_value = []
        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.get('/api/credit-score', headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        # A saved simulation takes priority over the computed baseline.
        self.assertEqual(body['score'], 720)
        self.assertTrue(300 <= body['base_score'] <= 850)

    def test_detect_subscriptions_flags_recurring_monthly_debit(self):
        base = datetime(2026, 7, 1)
        rows = [
            {'description': 'Netflix', 'category': 'Entertainment', 'transaction_amount': 499.0, 'timestamp': base, 'currency': 'INR'},
            {'description': 'Netflix', 'category': 'Entertainment', 'transaction_amount': 499.0, 'timestamp': base + timedelta(days=30), 'currency': 'INR'},
            {'description': 'Netflix', 'category': 'Entertainment', 'transaction_amount': 499.0, 'timestamp': base + timedelta(days=60), 'currency': 'INR'},
            {'description': 'Random Cafe', 'category': 'Food', 'transaction_amount': 350.0, 'timestamp': base + timedelta(days=12), 'currency': 'INR'},
        ]
        find_mock = Mock()
        find_mock.sort.return_value = rows
        self.db.transactions.find.return_value = find_mock

        subscriptions = application._detect_subscriptions(self.db, self.user_id)
        self.assertEqual(len(subscriptions), 1)
        sub = subscriptions[0]
        self.assertEqual(sub['label'], 'Netflix')
        self.assertEqual(sub['frequency'], 'monthly')
        self.assertEqual(sub['amount'], 499.0)
        self.assertAlmostEqual(sub['monthly_estimate'], 499.0, places=1)
        self.assertEqual(sub['next_expected'], base + timedelta(days=90))

    def test_detect_subscriptions_ignores_widely_varying_amounts(self):
        base = datetime(2026, 7, 1)
        rows = [
            {'description': 'Freelance Client', 'category': 'Income', 'transaction_amount': 1000.0, 'timestamp': base, 'currency': 'INR'},
            {'description': 'Freelance Client', 'category': 'Income', 'transaction_amount': 4000.0, 'timestamp': base + timedelta(days=45), 'currency': 'INR'},
        ]
        find_mock = Mock()
        find_mock.sort.return_value = rows
        self.db.transactions.find.return_value = find_mock
        self.assertEqual(application._detect_subscriptions(self.db, self.user_id), [])

    def test_notifications_includes_high_risk_transaction_and_budget_overage(self):
        self.db.users.find_one.return_value = {'budget_limit': 1000}
        high_risk_cursor = Mock()
        high_risk_cursor.sort.return_value.limit.return_value = [
            {'transaction_id': 'TXN-1', 'transaction_amount': 50000.0, 'channel': 'ATM', 'timestamp': datetime.now()},
        ]
        subs_cursor = Mock()
        subs_cursor.sort.return_value = []

        def find_side_effect(query, *args, **kwargs):
            if query.get('risk_level') == 'High':
                return high_risk_cursor
            return subs_cursor
        self.db.transactions.find.side_effect = find_side_effect
        self.db.transactions.aggregate.return_value = [{'total': 5000}]

        with patch.object(application, 'get_db', return_value=self.db):
            response = self.client.get('/api/notifications', headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        types = {n['type'] for n in body['notifications']}
        self.assertIn('fraud', types)
        self.assertIn('budget', types)
        self.assertGreaterEqual(body['new_count'], 1)

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