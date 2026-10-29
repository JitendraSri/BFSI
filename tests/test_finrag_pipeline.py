import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pymongo

with patch.object(pymongo, 'MongoClient'):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app as application

SEC_HTML = b"""<html><body>
<div style="display:none"><ix:header>hidden xbrl header</ix:header></div>
<div>Item 7. Management&#8217;s Discussion and Analysis</div>
<p>Net sales increased 5% driven by membership growth.</p>
<div style="page-break-after:always"></div>
<div>CONSOLIDATED STATEMENTS OF CASH FLOWS</div>
<div>(amounts in millions)</div>
<table>
<tr><td></td><td>2024</td><td>2023</td></tr>
<tr><td>Net income</td><td>$</td><td>7,367</td><td>$</td><td>6,292</td></tr>
<tr><td>Capital expenditures</td><td>(</td><td>4,710</td><td>)</td><td>(4,323</td><td>)</td></tr>
</table>
</body></html>"""


class ParsingAndChunkingTests(unittest.TestCase):
    def test_html_tables_are_kept_whole_with_page_section_and_units(self):
        blocks = application.parse_document('filing.html', SEC_HTML, 10_000_000)
        self.assertFalse(any('hidden xbrl' in b['text'] for b in blocks))
        chunks = application.make_chunks(blocks, 'filing.html')
        table = next(c for c in chunks if c['content_type'] == 'table')
        self.assertEqual(table['section'], 'CONSOLIDATED STATEMENTS OF CASH FLOWS')
        self.assertEqual(table['page'], 2)
        self.assertEqual(table['table'], 1)
        self.assertEqual(table['units'], 'millions')
        self.assertIn('Net income | $7,367 | $6,292', table['text'])
        text = next(c for c in chunks if c['content_type'] == 'text')
        self.assertTrue(text['section'].startswith('Item 7.'))

    def test_pdf_style_layout_text_detects_tables_but_not_justified_prose(self):
        page = ('Consolidated Statements of Operations\n(Dollars in millions)\n'
                'Years ended December 31,      2022       2021\n'
                'Revenues                   $66,608    $62,286\n'
                'Cost of sales               63,106     59,237\n\n'
                'Revenues   increased   by   $4,322   million   in   2022   compared   with   2021   driven   by   deliveries.\n')
        blocks = application.parse_document('x.txt', page.encode(), 10_000_000)
        tables = [b for b in blocks if b['type'] == 'table']
        self.assertEqual(len(tables), 1)
        self.assertIn('Revenues | $66,608 | $62,286', tables[0]['text'])
        self.assertNotIn('deliveries', tables[0]['text'])
        self.assertEqual(tables[0]['units'], '$ millions')

    def test_units_and_headings(self):
        self.assertEqual(application.detect_units('(Dollars in millions)'), '$ millions')
        self.assertEqual(application.detect_units('(₹ in crore)'), '₹ crores')
        self.assertTrue(application.is_section_heading('Item 1A—Risk Factors'))
        self.assertTrue(application.is_section_heading('Standalone Balance Sheet'))
        self.assertFalse(application.is_section_heading('Item 7 is discussed below. Revenue rose.'))

    def test_large_tables_are_split_with_header_repeated(self):
        rows = '\n'.join(f'Line item {i} | {i * 100:,} | {i * 90:,}' for i in range(400))
        chunks = application.make_chunks([{'type': 'table', 'text': 'Metric | 2024 | 2023\nSubtitle | | \n' + rows, 'page': 3}], 'doc')
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all('Metric | 2024 | 2023' in c['text'] for c in chunks))


class MetadataTests(unittest.TestCase):
    def test_indian_amounts_and_fiscal_years(self):
        self.assertEqual(application.parse_amount('₹1,23,456 crore'), 123456 * 1e7)
        self.assertEqual(application.parse_amount('Rs. 2.5 lakh'), 250000)
        self.assertEqual(application.normalize_period('FY 2023-24'), '2024')
        self.assertEqual(application.normalize_period("FY24"), '2024')
        entities = application.extract_entities('Reliance Industries Limited reported revenue of ₹9,74,864 crore in FY2023-24.')
        self.assertIn('Reliance Industries Limited', entities['organisations'])
        self.assertIn('2024', entities['fiscal_years'])
        self.assertIn('revenue', entities['metrics'])
        self.assertEqual(application.detect_market('₹ crore, listed on BSE and NSE, SEBI regulations'), 'India')


class RetrievalTests(unittest.TestCase):
    def test_metadata_reranker_uses_four_equal_components(self):
        candidates = [
            {'text': 'a', 'entities': ['Apple', 'revenue'], 'clusters': ['Financial Performance'], 'retrieval': 0.03},
            {'text': 'b', 'entities': ['Tesla'], 'clusters': ['Risk'], 'retrieval': 0.032},
            {'text': 'c', 'entities': ['Apple'], 'clusters': ['Financial Performance'], 'retrieval': 0.02},
        ]
        ranked = application.metadata_rerank(candidates, 'Apple revenue 2024')
        self.assertEqual(ranked[0]['text'], 'a')
        self.assertEqual(set(ranked[0]['rerank']), {'entity_freq', 'cluster_coherence', 'entity_query', 'retrieval'})
        self.assertAlmostEqual(ranked[0]['score'], 0.25 * sum(ranked[0]['rerank'].values()), places=3)

    def test_rrf_rewards_agreement_between_lists(self):
        order, scores = application.reciprocal_rank_fusion([(1.0, [2, 0, 1]), (1.0, [0, 2]), (1.0, [0])])
        self.assertEqual(order[0], 0)


class GenerationTests(unittest.TestCase):
    def test_numeric_grounding_flags_numbers_missing_from_sources(self):
        chunks = [{'text': 'Revenue was $66,608 million in 2022 and $62,286 million in 2021.'}]
        report = application.numeric_grounding('Revenue grew to $66,608 million [1], up from $61,000 million.', chunks)
        self.assertEqual(report['numbers_checked'], 2)
        self.assertEqual(report['unverified_numbers'], ['$61,000'])

    def test_numeric_grounding_accepts_correct_calculations_only(self):
        chunks = [{'text': 'Profit after tax | 27,234 | 24,108'}]
        report = application.numeric_grounding(
            'PAT rose ₹3,126 crore (12.97%) from ₹24,108 crore to ₹27,234 crore [1], x 100; margin 45.5%.', chunks)
        self.assertEqual(report['calculated_numbers'], ['₹3,126', '12.97%'])
        self.assertEqual(report['unverified_numbers'], ['45.5%'])

    def test_citation_labels_include_page_section_and_table(self):
        label = application.citation_label({'source': '10-K.pdf', 'page': 23, 'section': 'Item 8', 'table': 4})
        self.assertEqual(label, '10-K.pdf, p. 23, Item 8, Table 4')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = patch.object(application, 'STORAGE_ROOT', Path(self.directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_full_pipeline_uses_plan_dense_vectors_and_cites_tables(self):
        document = application.index_document('u1', 'filing.html', SEC_HTML)
        path = application._document_path('u1', document['id'])
        count = document['chunk_count']
        np.save(path.with_suffix('.npy'), np.eye(count, 8, dtype=np.float32))

        plan = {'rewritten_query': 'capital expenditures cash flow statement 2024',
                'hypothetical_answer': 'Capital expenditures were $4,710 million.', 'sub_questions': []}
        client = Mock()
        client.models.generate_content.side_effect = [
            SimpleNamespace(text=json.dumps(plan)),
            SimpleNamespace(text='Capital expenditures were $4,710 million in 2024 [1].'),
        ]
        client.models.embed_content.return_value = SimpleNamespace(
            embeddings=[SimpleNamespace(values=list(np.eye(count, 8)[-1])) for _ in range(3)])
        application._PLAN_CACHE.clear()
        with patch.object(application, 'get_client', return_value=client):
            answer = application.ask_document('u1', document['id'], 'What was capex in 2024?', 'key')

        self.assertTrue(answer['retrieval']['dense_used'])
        self.assertEqual(answer['retrieval']['query_plan']['rewritten_query'], plan['rewritten_query'])
        table_source = next(s for s in answer['sources'] if s['content_type'] == 'table')
        self.assertEqual(table_source['table'], 1)
        self.assertEqual(answer['grounding']['unverified_numbers'], [])
        self.assertIn(answer['confidence']['label'], {'low', 'medium', 'high'})

    def test_search_all_documents_uses_file_filter(self):
        first = application.index_document('u1', 'a.txt', b'Apple revenue was 383 billion in fiscal 2023.')
        application.index_document('u1', 'b.txt', b'Tesla delivered vehicles in 2023.')
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(text='Apple revenue was 383 billion [1].')
        with patch.object(application, 'get_client', return_value=client):
            answer = application.ask_document('u1', 'all', 'Apple revenue', 'key', options='sparse')
        self.assertEqual(answer['retrieval']['file_filter']['library_size'], 2)
        self.assertEqual(answer['sources'][0]['document_id'], first['id'])

    def _auth(self, user_id='u1'):
        import jwt
        application.limiter.enabled = False
        self.addCleanup(setattr, application.limiter, 'enabled', True)
        return {'Authorization': 'Bearer ' + jwt.encode({'user_id': user_id, 'email': f'{user_id}@example.test'},
                                                         application.SECRET_KEY, algorithm='HS256')}

    def test_streaming_answer_reports_real_stages_streams_tokens_and_saves_the_conversation(self):
        document = application.index_document('u1', 'filing.html', SEC_HTML)
        plan = {'rewritten_query': 'capital expenditures 2024', 'hypothetical_answer': '', 'sub_questions': []}
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(plan))
        client.models.generate_content_stream.return_value = iter([
            SimpleNamespace(text='Capital expenditures were '), SimpleNamespace(text='$4,710 million in 2024 [1].')])
        database = Mock()
        database.rag_conversations.update_one.return_value.matched_count = 0
        application._PLAN_CACHE.clear()
        with patch.object(application, 'get_client', return_value=client), \
             patch.object(application, 'get_db', return_value=database), \
             patch.object(application, '_gemini_key', return_value='key'):
            response = application.app.test_client().post(
                '/api/rag/ask/stream', headers=self._auth(),
                json={'document_id': document['id'], 'query': 'What was capex in 2024?', 'options': 'hybrid_rerank'})
            body = response.get_data(as_text=True)
        self.assertEqual(response.mimetype, 'text/event-stream')
        events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                  for block in body.strip().split('\n\n') if block.startswith('event:')]
        stages = [payload['stage'] for name, payload in events if name == 'stage']
        self.assertEqual(stages[:2], ['plan', 'retrieve'])
        self.assertIn('generate', stages)
        self.assertIn('verify', stages)
        tokens = ''.join(payload['text'] for name, payload in events if name == 'token')
        self.assertEqual(tokens, 'Capital expenditures were $4,710 million in 2024 [1].')
        done = events[-1][1]
        self.assertEqual(events[-1][0], 'done')
        self.assertEqual(done['answer'], tokens)
        self.assertEqual(done['sources'][0]['original'], 'html')
        self.assertRegex(done['conversation_id'], r'^[0-9a-f]{32}$')
        saved = database.rag_conversations.insert_one.call_args.args[0]
        self.assertEqual(saved['user_id'], 'u1')
        self.assertEqual([m['role'] for m in saved['messages']], ['user', 'assistant'])

    def test_original_document_links_are_signed_short_lived_and_sandboxed(self):
        document = application.index_document('u1', 'filing.html', SEC_HTML)
        test_client = application.app.test_client()
        opened = test_client.post(f"/api/rag/documents/{document['id']}/open", headers=self._auth())
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.get_json()['kind'], 'html')
        served = test_client.get(opened.get_json()['url'])
        self.assertEqual(served.status_code, 200)
        self.assertIn('sandbox', served.headers['Content-Security-Policy'])
        self.assertEqual(served.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn(b'Net income', served.data)
        served.close()  # release the file handle (Windows will not delete an open file)

        self.assertEqual(test_client.get(f"/rag/original/{document['id']}?t=forged").status_code, 403)
        sign_in_token = self._auth()['Authorization'].split(' ', 1)[1]
        self.assertEqual(test_client.get(f"/rag/original/{document['id']}?t={sign_in_token}").status_code, 403)
        other_user = test_client.post(f"/api/rag/documents/{document['id']}/open", headers=self._auth('u2'))
        self.assertEqual(other_user.status_code, 404)

        self.assertTrue(application.delete_document('u1', document['id']))
        self.assertIsNone(application.original_kind('u1', document['id']))

    def test_saved_conversations_are_owner_scoped(self):
        database = Mock()
        database.rag_conversations.find_one.return_value = None
        database.rag_conversations.delete_one.return_value.deleted_count = 0
        with patch.object(application, 'get_db', return_value=database):
            test_client = application.app.test_client()
            missing = test_client.get('/api/rag/conversations/' + 'a' * 32, headers=self._auth())
            not_deleted = test_client.delete('/api/rag/conversations/' + 'a' * 32, headers=self._auth())
            bad_id = test_client.get('/api/rag/conversations/../x', headers=self._auth())
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(not_deleted.status_code, 404)
        self.assertEqual(bad_id.status_code, 404)
        self.assertEqual(database.rag_conversations.find_one.call_args.args[0], {'conversation_id': 'a' * 32, 'user_id': 'u1'})

    def test_presets_resolve(self):
        self.assertFalse(application.resolve_options('sparse')['dense'])
        self.assertFalse(application.resolve_options('dense')['sparse'])
        self.assertTrue(application.resolve_options('full')['hyde'])


if __name__ == '__main__':
    unittest.main()
