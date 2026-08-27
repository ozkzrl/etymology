import os
import tempfile
import unittest

from engine.db.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp()
        self.db = DatabaseManager(db_path=self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_save_and_get_finding(self):
        finding_data = {
            "query_word": "göz",
            "root": {
                "proto_turkic": "*göŕ",
                "meaning": "eye / sight",
                "reconstruction_notes": "Test reconstruction"
            },
            "turkic_languages": [
                {"lang_code": "tr", "lang_name": "Türkiye Türkçesi", "word": "göz", "meaning": "göz", "script": "Latin"},
                {"lang_code": "az", "lang_name": "Azerbaycan Türkçesi", "word": "göz", "meaning": "göz", "script": "Latin"},
                {"lang_code": "kk", "lang_name": "Kazakça", "word": "көз", "meaning": "göz", "script": "Cyrillic"}
            ],
            "sources": ["Test Source"]
        }

        finding_id = self.db.save_finding(finding_data)
        self.assertIsInstance(finding_id, int)

        retrieved = self.db.get_finding("göz")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["query_word"], "göz")
        self.assertEqual(retrieved["root"]["proto_turkic"], "*göŕ")
        self.assertEqual(len(retrieved["turkic_languages"]), 3)

    def test_list_findings(self):
        finding1 = {"query_word": "el", "root": {"proto_turkic": "*el"}, "turkic_languages": []}
        finding2 = {"query_word": "su", "root": {"proto_turkic": "*sub"}, "turkic_languages": []}
        self.db.save_finding(finding1)
        self.db.save_finding(finding2)

        findings_list = self.db.list_findings()
        self.assertEqual(len(findings_list), 2)
        words = [f["query_word"] for f in findings_list]
        self.assertIn("el", words)
        self.assertIn("su", words)

if __name__ == "__main__":
    unittest.main()
