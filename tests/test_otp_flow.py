import contextlib
import io
import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymongo


_mock_client = Mock()
_mock_client.__getitem__ = Mock(return_value=Mock())
with patch.object(pymongo, 'MongoClient', return_value=_mock_client):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app as application


class OtpFlowTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.users = Mock()
        self.database = SimpleNamespace(users=self.users)
        self.get_db_patcher = patch.object(application, 'get_db', return_value=self.database)
        self.get_db_patcher.start()

    def tearDown(self):
        self.get_db_patcher.stop()

    def test_smtp_validation_and_brevo_starttls_credentials(self):
        self.assertEqual(
            application.validate_smtp_config(
                'smtp-relay.brevo.com', 587, 'smtp-user', 'smtp-key', 'sender@example.test'
            ),
            [],
        )
        self.assertIn(
            'SMTP_PORT must be 587',
            application.validate_smtp_config(
                'smtp-relay.brevo.com', 2525, 'smtp-user', 'smtp-key', 'sender@example.test'
            ),
        )
        self.assertIn(
            'SMTP_PASSWORD is required',
            application.validate_smtp_config(
                'smtp-relay.brevo.com', 587, 'smtp-user', '', 'sender@example.test'
            ),
        )

        smtp_server = Mock()
        smtp_context = Mock()
        smtp_context.__enter__ = Mock(return_value=smtp_server)
        smtp_context.__exit__ = Mock(return_value=False)
        with patch.object(application.smtplib, 'SMTP', return_value=smtp_context) as smtp:
            with patch.object(application, 'SMTP_LOGIN', 'smtp-user'), patch.object(
                application, 'SMTP_PASSWORD', 'smtp-key'
            ):
                self.assertTrue(application.send_otp_email('user@example.test', '123456'))
        smtp.assert_called_once_with('smtp-relay.brevo.com', 587, timeout=10)
        smtp_server.starttls.assert_called_once()
        smtp_server.login.assert_called_once_with('smtp-user', 'smtp-key')
        smtp_server.send_message.assert_called_once()

    def test_smtp_failure_logs_neither_credentials_nor_otp(self):
        smtp_server = Mock()
        smtp_server.login.side_effect = application.smtplib.SMTPAuthenticationError(535, b'auth rejected')
        smtp_context = Mock()
        smtp_context.__enter__ = Mock(return_value=smtp_server)
        smtp_context.__exit__ = Mock(return_value=False)
        with patch.object(application.smtplib, 'SMTP', return_value=smtp_context):
            with patch.object(application, 'SMTP_LOGIN', 'private-login'), patch.object(
                application, 'SMTP_PASSWORD', 'private-key'
            ):
                with self.assertLogs(application.logger, level='ERROR') as captured:
                    self.assertFalse(application.send_otp_email('user@example.test', '654321'))
        log_text = '\n'.join(captured.output)
        self.assertNotIn('private-login', log_text)
        self.assertNotIn('private-key', log_text)
        self.assertNotIn('654321', log_text)
        self.assertIn('authentication', log_text)
        self.assertIn('SMTPAuthenticationError', log_text)

    def test_failed_registration_keeps_account_and_offers_resend(self):
        self.users.find_one.return_value = None
        with patch.object(application, 'send_otp_email', return_value=False) as send_email:
            response = self.client.post('/register', json={
                'name': 'Test User',
                'email': 'user@example.test',
                'password': 'not-a-real-password',
                'initial_balance': 0,
            })

        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.get_json()['verification_pending'])
        inserted_user = self.users.insert_one.call_args.args[0]
        self.assertIn('otp_hash', inserted_user)
        self.assertNotIn('otp_code', inserted_user)
        send_email.assert_called_once()

    def test_resend_replaces_legacy_code_and_sets_expiry(self):
        now = datetime.datetime.now()
        self.users.find_one.return_value = {
            '_id': 'user-id',
            'email': 'user@example.test',
            'is_verified': False,
            'otp_code': 'old-code',
            'otp_last_sent': now - datetime.timedelta(seconds=61),
            'otp_resend_window_started_at': now - datetime.timedelta(minutes=5),
            'otp_resend_count': 1,
        }
        self.users.update_one.return_value = SimpleNamespace(matched_count=1)
        with patch.object(application, 'send_otp_email', return_value=True) as send_email:
            response = self.client.post('/resend-registration-otp', json={'email': 'user@example.test'})

        self.assertEqual(response.status_code, 200)
        update = self.users.update_one.call_args.args[1]
        self.assertIn('otp_hash', update['$set'])
        self.assertIn('otp_expiry', update['$set'])
        self.assertIn('otp_code', update['$unset'])
        send_email.assert_called_once()

    def test_resend_cooldown_prevents_send(self):
        self.users.find_one.return_value = {
            '_id': 'user-id',
            'email': 'user@example.test',
            'is_verified': False,
            'otp_last_sent': datetime.datetime.now() - datetime.timedelta(seconds=10),
            'otp_resend_window_started_at': datetime.datetime.now(),
            'otp_resend_count': 0,
        }
        with patch.object(application, 'send_otp_email') as send_email:
            response = self.client.post('/resend-registration-otp', json={'email': 'user@example.test'})
        self.assertEqual(response.status_code, 429)
        send_email.assert_not_called()
        self.users.update_one.assert_not_called()

    def test_resend_hourly_limit_prevents_send(self):
        now = datetime.datetime.now()
        self.users.find_one.return_value = {
            '_id': 'user-id',
            'email': 'user@example.test',
            'is_verified': False,
            'otp_last_sent': now - datetime.timedelta(seconds=61),
            'otp_resend_window_started_at': now - datetime.timedelta(minutes=20),
            'otp_resend_count': application.OTP_MAX_RESENDS_PER_HOUR,
        }
        with patch.object(application, 'send_otp_email') as send_email:
            response = self.client.post('/resend-registration-otp', json={'email': 'user@example.test'})
        self.assertEqual(response.status_code, 429)
        send_email.assert_not_called()
        self.users.update_one.assert_not_called()

    def test_hash_otp_verifies_and_invalidates_code(self):
        email = 'user@example.test'
        self.users.find_one.return_value = {
            'email': email,
            'is_verified': False,
            'otp_hash': application._otp_digest(email, '012345'),
            'otp_expiry': datetime.datetime.now() + datetime.timedelta(minutes=5),
        }
        response = self.client.post('/verify-registration', json={'email': email, 'otp': '012345'})
        self.assertEqual(response.status_code, 200)
        update = self.users.update_one.call_args.args[1]
        self.assertIn('otp_hash', update['$unset'])
        self.assertIn('otp_expiry', update['$unset'])

    def test_login_requires_verified_email_before_issuing_session(self):
        password_hash = application.bcrypt.hashpw(b'correct-password', application.bcrypt.gensalt()).decode('utf-8')
        user = {
            'user_id': 'user-id',
            'email': 'user@example.test',
            'password_hash': password_hash,
        }
        self.users.find_one.return_value = user
        for verification_value in (False, 0, None):
            user['is_verified'] = verification_value
            pending = self.client.post('/login', json={
                'email': 'user@example.test',
                'password': 'correct-password',
            })
            self.assertEqual(pending.status_code, 403)

        user.pop('is_verified')
        missing_status = self.client.post('/login', json={
            'email': 'user@example.test',
            'password': 'correct-password',
        })
        self.assertEqual(missing_status.status_code, 403)

        user['is_verified'] = True
        verified = self.client.post('/login', json={
            'email': 'user@example.test',
            'password': 'correct-password',
        })
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.get_json()['user']['is_verified'])

    def test_forgot_password_uses_separate_reset_otp_and_generic_response(self):
        self.users.find_one.return_value = {
            'user_id': 'user-id',
            'email': 'user@example.test',
            'is_verified': True,
        }
        self.users.update_one.return_value.matched_count = 1
        with patch.object(application, 'send_otp_email', return_value=True) as send_email:
            response = self.client.post('/forgot-password', json={'email': 'USER@example.test'})

        self.assertEqual(response.status_code, 202)
        self.assertIn('If a verified account exists', response.get_json()['message'])
        update = self.users.update_one.call_args.args[1]['$set']
        self.assertIn('password_reset_otp_hash', update)
        self.assertIn('password_reset_otp_expiry', update)
        self.assertNotIn('otp_hash', update)
        send_email.assert_called_once()

    def test_password_reset_consumes_only_reset_otp_and_preserves_verification(self):
        email = 'user@example.test'
        self.users.find_one.return_value = {
            'email': email,
            'is_verified': True,
            'otp_hash': application._otp_digest(email, '123456'),
            'otp_expiry': datetime.datetime.now() + datetime.timedelta(minutes=5),
            'password_reset_otp_hash': application._otp_digest(email, '654321'),
            'password_reset_otp_expiry': datetime.datetime.now() + datetime.timedelta(minutes=5),
        }
        self.users.update_one.return_value = SimpleNamespace(modified_count=1)

        response = self.client.post('/reset-password', json={
            'email': email,
            'otp': '654321',
            'new_password': 'a-long-new-password',
        })

        self.assertEqual(response.status_code, 200)
        update = self.users.update_one.call_args.args[1]
        self.assertIn('password_hash', update['$set'])
        self.assertNotIn('is_verified', update['$set'])
        self.assertIn('password_reset_otp_hash', update['$unset'])
        self.assertNotIn('otp_hash', update['$unset'])

    def test_password_reset_rejects_registration_otp_and_short_password(self):
        email = 'user@example.test'
        self.users.find_one.return_value = {
            'email': email,
            'is_verified': True,
            'otp_hash': application._otp_digest(email, '123456'),
            'otp_expiry': datetime.datetime.now() + datetime.timedelta(minutes=5),
        }

        registration_code = self.client.post('/reset-password', json={
            'email': email,
            'otp': '123456',
            'new_password': 'a-long-new-password',
        })
        self.assertEqual(registration_code.status_code, 400)

        short_password = self.client.post('/reset-password', json={
            'email': email,
            'otp': '654321',
            'new_password': 'short',
        })
        self.assertEqual(short_password.status_code, 400)
        self.users.update_one.assert_not_called()

    def test_password_reset_cannot_verify_an_unverified_account(self):
        email = 'pending@example.test'
        self.users.find_one.return_value = {
            'email': email,
            'is_verified': False,
            'password_reset_otp_hash': application._otp_digest(email, '654321'),
            'password_reset_otp_expiry': datetime.datetime.now() + datetime.timedelta(minutes=5),
        }
        response = self.client.post('/reset-password', json={
            'email': email,
            'otp': '654321',
            'new_password': 'a-long-new-password',
        })
        self.assertEqual(response.status_code, 400)
        self.users.update_one.assert_not_called()


if __name__ == '__main__':
    unittest.main()