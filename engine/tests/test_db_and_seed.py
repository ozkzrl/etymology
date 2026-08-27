"""
Kalıcılık, Tohum Veri ve Dışa/İçe Aktarım Testleri
"""
from __future__ import annotations

import csv
import gc
import io
import json
import os
import sqlite3
import tempfile
import unittest

from engine.db.cldf_exporter import CldfExporter
from engine.db.cldf_importer import CldfImporter
from engine.db.database import DatabaseManager
from engine.db.graph_database import GraphDatabaseManager
from engine.utils import seed


def make_finding(word="göz"):
    return {
        "query_word": word,
        "morphology": "Yalın Kök",
        "root": {"proto_turkic": "*köŕ", "meaning": "göz", "reconstruction_notes": "rotasizm"},
        "turkic_languages": [
            {"lang_code": "tr", "lang_name": "Türkiye Türkçesi", "word": word,
             "meaning": "göz", "script": "Latin"},
            {"lang_code": "kk", "lang_name": "Kazakça", "word": "көз",
             "meaning": "göz", "script": "Cyrillic"},
        ],
        "sources": ["TDK"],
    }


class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = DatabaseManager(self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_save_and_get(self):
        self.db.save_finding(make_finding())
        stored = self.db.get_finding("göz")
        self.assertEqual(stored["root"]["proto_turkic"], "*köŕ")

    def test_update_replaces_entries(self):
        self.db.save_finding(make_finding())
        updated = make_finding()
        updated["turkic_languages"] = updated["turkic_languages"][:1]
        self.db.save_finding(updated)
        self.assertEqual(len(self.db.get_finding("göz")["turkic_languages"]), 1)

    def test_list_findings(self):
        self.db.save_finding(make_finding("göz"))
        self.db.save_finding(make_finding("deniz"))
        words = {f["query_word"] for f in self.db.list_findings()}
        self.assertEqual(words, {"göz", "deniz"})

    def test_missing_word_returns_none(self):
        self.assertIsNone(self.db.get_finding("yokboyle"))

    def test_empty_query_word_raises(self):
        with self.assertRaises(ValueError):
            self.db.save_finding({"query_word": "", "root": {}, "turkic_languages": []})

    def test_ttl_cache_expiry(self):
        self.db.save_finding(make_finding())
        self.assertIsNotNone(self.db.get_finding("göz", max_age_seconds=3600))
        self.assertIsNone(self.db.get_finding("göz", max_age_seconds=0))

    def test_no_connection_leak(self):
        """Regresyon: `with sqlite3.connect(...)` bağlantıyı KAPATMAZ;
        her çağrıda bir bağlantı sızıyordu."""
        self.db.save_finding(make_finding())
        gc.collect()
        before = sum(1 for o in gc.get_objects() if isinstance(o, sqlite3.Connection))
        for _ in range(60):
            self.db.get_finding("göz")
            self.db.list_findings()
        gc.collect()
        after = sum(1 for o in gc.get_objects() if isinstance(o, sqlite3.Connection))
        self.assertLessEqual(after - before, 2)

    def test_corrupt_json_returns_none(self):
        self.db.save_finding(make_finding())
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE findings SET full_finding_json = '}{' WHERE query_word = 'göz'")
        self.assertIsNone(self.db.get_finding("göz"))


class TestCldfExporter(unittest.TestCase):
    def test_produces_valid_csv(self):
        bundle = CldfExporter().export_to_cldf(make_finding())
        rows = list(csv.DictReader(io.StringIO(bundle["cldf_forms_csv"])))
        self.assertEqual(len(rows), 2)
        self.assertIn("Language_ID", rows[0])
        self.assertEqual(bundle["metadata"]["cldfVersion"], "1.2")

    def test_cognate_table(self):
        bundle = CldfExporter().export_to_cldf(make_finding())
        rows = list(csv.DictReader(io.StringIO(bundle["cldf_cognates_csv"])))
        self.assertEqual(len(rows), 2)

    def test_empty_finding(self):
        bundle = CldfExporter().export_to_cldf({"query_word": "x", "turkic_languages": [], "root": {}})
        self.assertIn("ID", bundle["cldf_forms_csv"])


class TestCldfImporter(unittest.TestCase):
    """WOLD gibi harici CLDF veri kümelerinin içe alımı (plan §1.2)."""

    def _dataset(self, tmp):
        (tmp / "forms.csv").write_text(
            "ID,Language_ID,Parameter_ID,Form,Value\n"
            "f1,tur,kitap,kitap,kitap\n"
            "f2,arb,kitab,kitāb,kitāb\n",
            encoding="utf-8",
        )
        (tmp / "borrowings.csv").write_text(
            "ID,Target_Form_ID,Source_Form_ID,Comment,Source\n"
            "b1,f1,f2,yazılan şey,WOLD\n",
            encoding="utf-8",
        )
        return tmp

    def test_imports_borrowings(self):
        import pathlib

        with tempfile.TemporaryDirectory() as d:
            ds = self._dataset(pathlib.Path(d))
            entries = CldfImporter(ds).to_donor_entries("tur")
            self.assertIn("kitap", entries)
            self.assertEqual(entries["kitap"]["donor_lang"], "arb")
            self.assertEqual(entries["kitap"]["original_script"], "kitāb")

    def test_missing_tables_return_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(CldfImporter(d).read_forms(), [])
            self.assertEqual(CldfImporter(d).read_borrowings(), [])
            self.assertEqual(CldfImporter(d).to_donor_entries(), {})

    def test_language_name_mapping(self):
        import pathlib

        with tempfile.TemporaryDirectory() as d:
            ds = self._dataset(pathlib.Path(d))
            entries = CldfImporter(ds).to_donor_entries("tur", {"arb": "Arapça"})
            self.assertEqual(entries["kitap"]["donor_lang"], "Arapça")


class TestGraphDatabase(unittest.TestCase):
    def test_builds_nodes_and_edges(self):
        g = GraphDatabaseManager().build_etymology_graph(
            word="göz", root_form="*köŕ",
            hypothesis={"donor_language": "Proto-Türkçe", "confidence_score": 0.8},
            attestations=["1074 DLT"], cognates=["көз"],
        )
        self.assertTrue(g["graph_data"]["nodes"])
        self.assertTrue(g["graph_data"]["edges"])
        self.assertEqual(g["node_count"], len(g["graph_data"]["nodes"]))

    def test_handles_none_hypothesis(self):
        """Kanıt yoksa hipotez üretilmez; graf yine kurulmalıdır."""
        g = GraphDatabaseManager().build_etymology_graph(
            word="zzz", root_form="", hypothesis=None, attestations=[], cognates=[]
        )
        self.assertTrue(g["graph_data"]["nodes"])

    def test_no_fabricated_confidence(self):
        """Regresyon: hipotez yoksa graf düğümüne varsayılan 0.90 yazılıyordu."""
        g = GraphDatabaseManager().build_etymology_graph(
            word="zzz", root_form="", hypothesis={}, attestations=[], cognates=[]
        )
        blob = json.dumps(g)
        for node in g["graph_data"]["nodes"]:
            score = node.get("properties", {}).get("confidence_score")
            self.assertNotEqual(score, 0.90, blob[:200])

    def test_node_ids_are_safe(self):
        """Boşluk/özel karakter içeren kelimeler bozuk seçici üretmemelidir."""
        g = GraphDatabaseManager().build_etymology_graph(
            word="iki kelime!", root_form="*a b", hypothesis={}, attestations=[], cognates=[]
        )
        for node in g["graph_data"]["nodes"]:
            self.assertNotIn(" ", node["id"])
            self.assertNotIn("!", node["id"])


class TestSeedLoader(unittest.TestCase):
    def setUp(self):
        seed.clear_cache()

    def tearDown(self):
        seed.clear_cache()

    def test_loads_real_seed_files(self):
        entries = seed.load_seed_entries("donor/donor_etymology.json")
        self.assertIn("kitap", entries)
        prov = seed.load_seed_provenance("donor/donor_etymology.json")
        self.assertEqual(prov["kind"], "seed")

    def test_missing_file_returns_empty(self):
        self.assertEqual(seed.load_seed_entries("yok/olmayan.json"), {})
        self.assertEqual(seed.load_seed_provenance("yok/olmayan.json"), {})

    def test_source_label_declares_seed(self):
        label = seed.seed_source_label("Kaynak", "donor/donor_etymology.json")
        self.assertIn("tohum", label)
        self.assertIn("kayıt", label)

    def test_all_seed_files_have_provenance(self):
        """Her tohum dosyası kaynak künyesi taşımalıdır."""
        from engine.config import SEED_DIR

        for path in SEED_DIR.rglob("*.json"):
            with self.subTest(file=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("_provenance", data, path.name)
                self.assertIn("entries", data, path.name)
                self.assertTrue(data["_provenance"].get("source"), path.name)

    def test_corrupt_seed_file_is_handled(self, ):
        import pathlib
        import tempfile as tf

        with tf.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "bad.json").write_text("}{", encoding="utf-8")
            original = seed.SEED_DIR
            try:
                seed.SEED_DIR = tmp
                seed.clear_cache()
                self.assertEqual(seed.load_seed_entries("bad.json"), {})
            finally:
                seed.SEED_DIR = original
                seed.clear_cache()


if __name__ == "__main__":
    unittest.main()
