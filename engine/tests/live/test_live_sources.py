"""
Canlı Kaynak Testleri (Live Source Tests)

Bu testler GERÇEK ağa çıkar ve yalnızca ``ETY_LIVE=1`` ile çalışır::

    ETY_LIVE=1 pytest engine/tests/live -v

CI'da otomatik atlanır. Amaçları:

* dış kaynakların hâlâ ayakta ve ayrıştırılabilir olduğunu doğrulamak
* fixture'ların bayatladığını erken fark etmek
* ölü uç noktaları tespit etmek (5 tanesi bu şekilde bulunup kaldırıldı)
"""
from __future__ import annotations

import os
import unittest

from engine.fetchers.etimoloji_turkce import EtimolojiTurkceFetcher
from engine.fetchers.tdk_historical import TdkDerlemeFetcher
from engine.fetchers.tdk_nisanyan import NisanyanFetcher, TdkFetcher
from engine.fetchers.wiktextract_local import WiktextractFetcher
from engine.fetchers.wiktionary import WiktionaryFetcher
from engine.search_engine import SearchEngine, default_fetchers

LIVE = os.environ.get("ETY_LIVE") == "1"
requires_live = unittest.skipUnless(LIVE, "Canlı ağ testi — ETY_LIVE=1 ile çalıştırın")


@requires_live
class TestLiveFetchers(unittest.TestCase):
    """Her canlı kaynak hâlâ veri döndürüyor mu?"""

    def test_tdk_gts(self):
        res = TdkFetcher().fetch("deniz")
        self.assertTrue(res["turkic_languages"], "TDK GTS veri döndürmedi")
        self.assertTrue(res["root"]["meaning"])

    def test_tdk_derleme(self):
        self.assertIn("root", TdkDerlemeFetcher().fetch("göz"))

    def test_nisanyan(self):
        self.assertIn("root", NisanyanFetcher().fetch("deniz"))

    def test_wiktionary_proto_root(self):
        res = WiktionaryFetcher().fetch("göz")
        self.assertTrue(res["root"]["proto_turkic"], "Wiktionary proto kök bulamadı")

    def test_wiktextract(self):
        self.assertIn("root", WiktextractFetcher().fetch("göz"))

    def test_etimolojiturkce_attestation(self):
        res = EtimolojiTurkceFetcher().fetch("deniz")
        att = res.get("first_attestation")
        self.assertIsNotNone(att, "tarihli tanıklama çıkarılamadı")
        self.assertIsNotNone(att["year"])


@requires_live
class TestLiveSearchPipeline(unittest.TestCase):
    def test_full_search_returns_live_data(self):
        engine = SearchEngine(fetchers=default_fetchers())
        res = engine.search("deniz", save_to_db=False)
        diag = res["diagnostics"]
        self.assertGreater(diag["live_source_count"], 0, "hiçbir kaynak veri döndürmedi")
        self.assertTrue(res["turkic_languages"])

    def test_search_completes_within_budget(self):
        import time

        engine = SearchEngine(fetchers=default_fetchers())
        started = time.perf_counter()
        engine.search("göz", save_to_db=False)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 45.0, f"arama çok yavaş: {elapsed:.1f}s")


@requires_live
class TestLiveOllama(unittest.TestCase):
    def test_agent_availability_probe(self):
        from engine.llm.qwen_agent import QwenEtymologyAgent

        self.assertIsInstance(QwenEtymologyAgent().is_available(), bool)


if __name__ == "__main__":
    unittest.main()
