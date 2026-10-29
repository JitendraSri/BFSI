import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymongo

with patch.object(pymongo, 'MongoClient'):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import app as application


class RagDeletionTests(unittest.TestCase):
    def test_only_owner_can_delete_indexed_document_and_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(application, 'STORAGE_ROOT', Path(directory)):
                document = application.index_document(
                    'owner-a', 'report.txt', b'Quarterly revenue was 100 million.'
                )
                self.assertEqual(len(application.list_documents('owner-a')), 1)
                self.assertFalse(application.delete_document('owner-b', document['id']))
                self.assertEqual(len(application.list_documents('owner-a')), 1)
                self.assertTrue(application.delete_document('owner-a', document['id']))
                self.assertEqual(application.list_documents('owner-a'), [])
                self.assertFalse(application.delete_document('owner-a', '../outside'))


if __name__ == '__main__':
    unittest.main()
