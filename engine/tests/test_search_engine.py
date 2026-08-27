"""
SearchEngine Entegrasyon Testleri

Eski test canlı ağa çıkıyor, ~80 HTTP isteği atıyor ve 30-60 saniye sürüyordu.
``SearchEngine`` artık fetcher enjeksiyonuna izin verdiği için (``fetchers=``)
tüm entegrasyon ağsız ve milisaniyeler içinde koşar.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from engine import config
from engine.db.database import DatabaseManager
from engine.search_engine import SearchEngine, default_fetchers, translate_meaning
from engine.tests.fakes import EmptyFetcher, FailingFetcher, FakeFetcher

GOZ_FORMS = [("tr", "göz"), ("az", "göz"), ("kk", "көз"), ("tt", "күз"),
             ("cv", "куҫ"), ("otk", "köz"), ("ky", "көз"), ("ba", "күҙ")]


class TestSearchEngineIntegration(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _engine(self, fetchers):
        return SearchEngine(db_manager=self.db, fetchers=fetchers)

    def _goz_fetcher(self, **kw):
        return FakeFetcher(
            name="Sahte Sözlük", entries=GOZ_FORMS,
            meaning="göz, görme organı", only_for="göz", **kw
        )

    # --- Temel akış ------------------------------------------------------

    def test_search_produces_correct_reconstruction(self):
        res = self._engine([self._goz_fetcher()]).search("göz", save_to_db=False)
        self.assertEqual(res["root"]["proto_turkic"], "*köŕ")
        real = [e for e in res["turkic_languages"] if e["lang_code"] != "donor"]
        self.assertEqual(len(real), 8)

    def test_result_is_deterministic(self):
        """Aynı girdi -> BİREBİR aynı çıktı.

        Regresyon: hash() tohumlaması ve set sıralaması yüzünden skorlar ve
        aranan varyantlar her çalıştırmada değişiyordu.
        """
        import json

        engine = self._engine([self._goz_fetcher()])
        a = json.dumps(self._strip_timings(engine.search("göz", save_to_db=False)), sort_keys=True)
        b = json.dumps(self._strip_timings(engine.search("göz", save_to_db=False)), sort_keys=True)
        self.assertEqual(a, b)

    @staticmethod
    def _strip_timings(finding):
        f = dict(finding)
        f.pop("diagnostics", None)
        return f

    def test_failing_fetcher_does_not_break_search(self):
        """Bir kaynak çökerse arama DEVAM etmeli, hata GÖRÜNÜR olmalı."""
        engine = self._engine([self._goz_fetcher(), FailingFetcher(), EmptyFetcher()])
        res = engine.search("göz", save_to_db=False)
        real = [e for e in res["turkic_languages"] if e["lang_code"] != "donor"]
        self.assertEqual(len(real), 8)
        diag = res["diagnostics"]["sources"]
        self.assertEqual(diag["Patlayan Kaynak"]["status"], "error")
        self.assertTrue(diag["Patlayan Kaynak"]["errors"])
        self.assertEqual(diag["Boş Kaynak"]["status"], "empty")

    def test_diagnostics_report_real_timings(self):
        """Teşhis GERÇEK aşama sürelerini taşımalıdır (panelin sahte
        setTimeout simülasyonunun yerini alan veri)."""
        res = self._engine([self._goz_fetcher()]).search("göz", save_to_db=False)
        timings = res["diagnostics"]["stage_timings_ms"]
        for stage in ("morphology", "fetch", "nlp", "total"):
            self.assertIn(stage, timings)
            self.assertIsInstance(timings[stage], int)

    def test_variant_count_is_capped(self):
        res = self._engine([self._goz_fetcher()]).search("göz", save_to_db=False)
        self.assertLessEqual(len(res["diagnostics"]["variants_used"]), config.MAX_VARIANTS)

    # --- Uydurma üretmeme ------------------------------------------------

    def test_unknown_word_gets_no_fabricated_root(self):
        """Kanıt yoksa `*<kelime>` biçiminde ata kök UYDURULMAMALIDIR."""
        res = self._engine([EmptyFetcher()]).search("zzzqx", save_to_db=False)
        self.assertNotEqual(res["root"]["proto_turkic"], "*zzzqx")
        hypo = res["nlp_analysis"]["proven_hypothesis"]
        if hypo and hypo.get("validation_report"):
            self.assertNotIn("VALIDATED (kanıta dayalı)", hypo["validation_report"]["badge"])

    def test_unknown_word_badge_is_not_validated(self):
        res = self._engine([EmptyFetcher()]).search("qqqwwweee", save_to_db=False)
        hypo = res["nlp_analysis"]["proven_hypothesis"] or {}
        report = hypo.get("validation_report") or {}
        self.assertNotEqual(report.get("status_code"), "VALIDATED")

    # --- Önbellek --------------------------------------------------------

    def test_cache_round_trip(self):
        engine = self._engine([self._goz_fetcher()])
        first = engine.search("göz", save_to_db=True)
        self.assertFalse(first["from_cache"])
        second = engine.search("göz", save_to_db=True)
        self.assertTrue(second["from_cache"])
        self.assertEqual(second["root"]["proto_turkic"], first["root"]["proto_turkic"])

    def test_cache_can_be_disabled(self):
        engine = self._engine([self._goz_fetcher()])
        engine.search("göz", save_to_db=True)
        original = config.CACHE_ENABLED
        try:
            config.CACHE_ENABLED = False
            self.assertFalse(engine.search("göz", save_to_db=False)["from_cache"])
        finally:
            config.CACHE_ENABLED = original

    # --- Zenginleştirme --------------------------------------------------

    def test_entries_get_transliteration_and_references(self):
        """README'nin vaat ettiği transkripsiyon motoru boru hattına BAĞLI olmalı."""
        res = self._engine([self._goz_fetcher()]).search("göz", save_to_db=False)
        cyrillic = [e for e in res["turkic_languages"] if e.get("script") == "Cyrillic"]
        self.assertTrue(cyrillic)
        self.assertTrue(any("latin_transliteration" in e for e in cyrillic))

    def test_faz6_modules_are_wired(self):
        res = self._engine([self._goz_fetcher()]).search("göz", save_to_db=False)
        nlp = res["nlp_analysis"]
        for key in ("loanword_detection", "cognate_clusters", "historical_morphology",
                    "induced_sound_laws", "proven_hypothesis"):
            self.assertIn(key, nlp)

    def test_query_length_is_capped(self):
        res = self._engine([EmptyFetcher()]).search("a" * 500, save_to_db=False)
        self.assertLessEqual(len(res["query_word"]), config.MAX_QUERY_LENGTH)

    def test_empty_query(self):
        res = self._engine([EmptyFetcher()]).search("", save_to_db=False)
        self.assertEqual(res["query_word"], "")

    # --- Kalıcılık -------------------------------------------------------

    def test_saved_finding_round_trips(self):
        engine = self._engine([self._goz_fetcher()])
        engine.search("göz", save_to_db=True)
        stored = self.db.get_finding("göz")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["root"]["proto_turkic"], "*köŕ")


class TestTranslateMeaning(unittest.TestCase):
    def test_whole_word_matching(self):
        """Regresyon: substring eşleşmesi 'Sunday' -> 'güneş, gün' yapıyordu."""
        self.assertEqual(translate_meaning("sun"), "güneş, gün")
        self.assertEqual(translate_meaning("Sunday"), "Sunday")
        self.assertEqual(translate_meaning("consumed"), "consumed")
        self.assertEqual(translate_meaning("sunset glow"), "sunset glow")

    def test_phrase_matching(self):
        self.assertEqual(translate_meaning("the sea"), "deniz, büyük göl")

    def test_wiki_markup_stripped(self):
        self.assertNotIn("{{", translate_meaning("{{lb|tr}} eye"))

    def test_online_placeholder_passthrough(self):
        self.assertTrue(translate_meaning("Online Kazakça").startswith("Online"))

    def test_empty(self):
        self.assertEqual(translate_meaning(""), "")


class TestDefaultPortfolio(unittest.TestCase):
    def test_portfolio_instantiates(self):
        fetchers = default_fetchers()
        self.assertGreaterEqual(len(fetchers), 15)
        for f in fetchers:
            self.assertTrue(f.source_name)


if __name__ == "__main__":
    unittest.main()
