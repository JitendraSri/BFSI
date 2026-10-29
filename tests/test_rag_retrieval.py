import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymongo

with patch.object(pymongo, 'MongoClient'):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app as application


def mock_gemini(text):
    """Patch the shared Gemini client so generate_content returns the given text."""
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=text)
    return client, patch.object(application, 'get_client', return_value=client)


def sent_prompt(client):
    return client.models.generate_content.call_args.kwargs['contents']


class RagRetrievalTests(unittest.TestCase):
    def test_hybrid_ranking_prefers_passages_matching_the_full_query(self):
        chunks = [
            {'text': 'The report disclosed a liquidity covenant breach after year end.'},
            {'text': 'Liquidity and cash flow remained important priorities.'},
            {'text': 'The company expanded its regional customer support program.'},
        ]

        ranked = application._rank_chunks(chunks, 'liquidity covenant breach')

        self.assertTrue(ranked)
        self.assertEqual(ranked[0][0], 0)
        self.assertEqual(len(ranked), 2)

    def test_hybrid_ranking_returns_no_passages_without_lexical_overlap(self):
        chunks = [{'text': 'Operating revenue increased during the fiscal year.'}]

        self.assertEqual(application._rank_chunks(chunks, 'unmatched terminology'), [])

    def test_document_answer_reports_retrieval_method_and_source_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(application, 'STORAGE_ROOT', Path(directory)):
                document = application.index_document(
                    'reviewer', 'annual-report.txt',
                    b'Liquidity reserves were maintained throughout the fiscal year.'
                )
                client, gemini = mock_gemini('The report says liquidity reserves were maintained [1].')
                with gemini:
                    answer = application.ask_document(
                        'reviewer', document['id'], 'liquidity reserves', 'test-api-key'
                    )

        self.assertEqual(answer['retrieval']['method'], 'BM25 + TF-IDF with RRF fusion and metadata reranking')
        self.assertEqual(answer['retrieval']['passages_considered'], 1)
        self.assertEqual(answer['retrieval']['passages_retrieved'], 1)
        self.assertEqual(answer['sources'][0]['name'], 'annual-report.txt')

    def test_chat_without_selected_document_answers_greetings_with_gemini(self):
        client, gemini = mock_gemini('Hi! How can I help you today?')
        with gemini:
            answer = application.ask_document('', '', 'Hi', 'test-api-key')

        self.assertEqual(answer['mode'], 'conversation')
        self.assertEqual(answer['answer'], 'Hi! How can I help you today?')
        self.assertEqual(answer['sources'], [])
        self.assertNotIn('retrieval', answer)
        self.assertIn('Respond naturally', sent_prompt(client))

    def test_general_chat_uses_recent_conversation_for_followups(self):
        client, gemini = mock_gemini('The revenue was $10 million.')
        history = [
            {'role': 'user', 'content': 'What was the revenue?'},
            {'role': 'assistant', 'content': 'It was $10 million.'},
        ]
        with gemini:
            application.ask_document('', '', 'Tell me more.', 'test-api-key', chat_history=history)

        prompt = sent_prompt(client)
        self.assertIn('User: What was the revenue?', prompt)
        self.assertIn('Assistant: It was $10 million.', prompt)
        self.assertIn('User: Tell me more.', prompt)

    def test_document_question_without_matching_passages_gets_general_ai_response(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(application, 'STORAGE_ROOT', Path(directory)):
                document = application.index_document(
                    'reviewer', 'annual-report.txt',
                    b'Liquidity reserves were maintained throughout the fiscal year.'
                )
                client, gemini = mock_gemini('Inflation is a general rise in prices over time.')
                with gemini:
                    answer = application.ask_document(
                        'reviewer', document['id'], 'Explain inflation simply', 'test-api-key'
                    )

        self.assertEqual(answer['mode'], 'conversation')
        self.assertEqual(answer['intent'], 'general_knowledge')
        self.assertEqual(answer['retrieval']['passages_retrieved'], 0)
        self.assertEqual(answer['sources'], [])
        self.assertIn('Answer general finance', sent_prompt(client))

    def test_greeting_with_a_document_selected_skips_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(application, 'STORAGE_ROOT', Path(directory)):
                document = application.index_document(
                    'reviewer', 'AMAZON.txt', b'Amazon net sales were 638 billion in 2024.'
                )
                client, gemini = mock_gemini('Hi! Ask me about Amazon revenue, risks or cash flow.')
                with gemini:
                    answer = application.ask_document('reviewer', document['id'], 'hi', 'test-api-key')

        self.assertEqual(answer['mode'], 'conversation')
        self.assertEqual(answer['intent'], 'small_talk')
        self.assertNotIn('retrieval', answer)
        self.assertEqual(client.models.generate_content.call_count, 1)  # no planning call
        self.assertIn('AMAZON.txt', sent_prompt(client))

    def test_small_talk_detection(self):
        for text in ('hi', 'Hello there!', 'thanks so much', 'what can you do?', 'good morning'):
            self.assertTrue(application.is_small_talk(text), text)
        for text in ('what is EBITDA', 'hi, what was revenue in 2024?', 'revenue growth'):
            self.assertFalse(application.is_small_talk(text), text)

    def test_general_explanations_are_not_figure_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(application, 'STORAGE_ROOT', Path(directory)):
                document = application.index_document(
                    'reviewer', 'report.txt', b'EBITDA was 1,200 million in fiscal 2024.'
                )
                client, gemini = mock_gemini(
                    '**In general:** EBITDA = 500 + 300 + 200 for an example company.\n'
                    '**In this document:** EBITDA was 1,200 million [1].')
                with gemini:
                    answer = application.ask_document('reviewer', document['id'], 'what is EBITDA', 'test-api-key')
        self.assertEqual(answer['grounding']['unverified_numbers'], [])
        self.assertEqual(answer['grounding']['numbers_grounded'], 1)


if __name__ == '__main__':
    unittest.main()
