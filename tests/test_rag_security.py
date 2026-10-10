import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import rag_service


class RagDeletionTests(unittest.TestCase):
    def test_only_owner_can_delete_indexed_document_and_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(rag_service, 'STORAGE_ROOT', Path(directory)):
                document = rag_service.index_document(
                    'owner-a', 'report.txt', b'Quarterly revenue was 100 million.'
                )
                self.assertEqual(len(rag_service.list_documents('owner-a')), 1)
                self.assertFalse(rag_service.delete_document('owner-b', document['id']))
                self.assertEqual(len(rag_service.list_documents('owner-a')), 1)
                self.assertTrue(rag_service.delete_document('owner-a', document['id']))
                self.assertEqual(rag_service.list_documents('owner-a'), [])
                self.assertFalse(rag_service.delete_document('owner-a', '../outside'))


if __name__ == '__main__':
    unittest.main()