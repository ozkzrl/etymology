"""
Tüm Veri Toplayıcıların Testleri (All Fetchers)

18 fetcher'ın 15'i daha önce **hiç test edilmemişti**. Canlı HTTP çağrıları
``responses`` ile kayıtlı gerçek yanıtlarla oynatılır; testler ağsız çalışır.

Sözleşme kuralı her fetcher için doğrulanır:
``fetch()`` asla istisna fırlatmaz, her zaman
``{"root": {...}, "turkic_languages": [...]}`` döndürür.
"""
from __future__ import annotations

import re
import unittest

import responses

from engine.fetchers.academic_turkology import AcademicTurkologyFetcher
from engine.fetchers.archive_org import ArchiveOrgFetcher
from engine.fetchers.base import (
    TURKIC_LANGUAGES_MAP,
    BaseFetcher,
    detect_script,
    lang_code_from_wiktionary_header,
)
from engine.fetchers.etimoloji_turkce import EtimolojiTurkceFetcher
from engine.fetchers.historical_modern import HistoricalModernLexiconFetcher
from engine.fetchers.isam_ansiklopedi import IsamAnsiklopediFetcher
from engine.fetchers.loanword_donor_etymology import LoanwordDonorEtymologyFetcher
from engine.fetchers.local_pdf_books import LocalPdfBooksFetcher
from engine.fetchers.multilang_wiktionary import MultiLangWiktionaryFetcher
from engine.fetchers.osmanlica_lugat import OsmanlicaLugatFetcher
from engine.fetchers.starling import StarlingFetcher
from engine.fetchers.tdk_historical import TdkDerlemeFetcher, TdkTaramaFetcher
from engine.fetchers.tdk_nisanyan import NisanyanFetcher, TdkFetcher
from engine.fetchers.tietze_altaica import TietzeAltaicaFetcher
from engine.fetchers.turkic_national_dictionaries import TurkicNationalDictionariesFetcher
from engine.fetchers.wiktextract_local import WiktextractFetcher
from engine.fetchers.wiktionary import WiktionaryFetcher
from engine.search_engine import default_fetchers
from engine.tests.conftest import load_http_fixture
from engine.utils import network

#: Ağ gerektirmeyen (tohum veri) toplayıcılar
OFFLINE_FETCHERS = [
    AcademicTurkologyFetcher,
    HistoricalModernLexiconFetcher,
    StarlingFetcher,
    TietzeAltaicaFetcher,
    TurkicNationalDictionariesFetcher,
    LoanwordDonorEtymologyFetcher,
    LocalPdfBooksFetcher,
]

#: Ağ gerektiren toplayıcılar
NETWORK_FETCHERS = [
    ArchiveOrgFetcher,
    EtimolojiTurkceFetcher,
    IsamAnsiklopediFetcher,
    MultiLangWiktionaryFetcher,
    OsmanlicaLugatFetcher,
    TdkFetcher,
    NisanyanFetcher,
    TdkTaramaFetcher,
    TdkDerlemeFetcher,
    WiktionaryFetcher,
    WiktextractFetcher,
]

ALL_FETCHERS = OFFLINE_FETCHERS + NETWORK_FETCHERS


def assert_contract(testcase: unittest.TestCase, result, who: str) -> None:
    """BaseFetcher dönüş sözleşmesini doğrular."""
    testcase.assertIsInstance(result, dict, who)
    testcase.assertIn("root", result, who)
    testcase.assertIn("turkic_languages", result, who)
    root = result["root"]
    for key in ("proto_turkic", "meaning", "reconstruction_notes"):
        testcase.assertIn(key, root, f"{who}: root.{key}")
    testcase.assertIsInstance(result["turkic_languages"], list, who)
    for entry in result["turkic_languages"]:
        for key in ("lang_code", "lang_name", "word", "meaning", "script"):
            testcase.assertIn(key, entry, f"{who}: entry.{key}")


class TestBaseFetcherContract(unittest.TestCase):
    """BaseFetcher sözleşmesi ve yardımcıları."""

    def test_language_map_has_25_languages(self):
        """README '25 Türki dil' diyordu ama harita 18 kod içeriyordu."""
        self.assertEqual(len(TURKIC_LANGUAGES_MAP), 25)
        for code in ("nog", "kum", "crh", "kaa", "cjs", "ota", "slq"):
            self.assertIn(code, TURKIC_LANGUAGES_MAP, code)

    def test_wiktionary_header_mapping(self):
        """İngilizce Wiktionary başlıkları dil koduna eşlenmelidir.

        Regresyon: başlıklar Türkçe dil ADLARIYLA karşılaştırılıyordu,
        hiçbir zaman eşleşmiyordu ve kelime sayfası ayrıştırıcısı ölüydü.
        """
        self.assertEqual(lang_code_from_wiktionary_header("==Turkish=="), "tr")
        self.assertEqual(lang_code_from_wiktionary_header("Kazakh"), "kk")
        self.assertEqual(lang_code_from_wiktionary_header("Old Turkic"), "otk")
        self.assertEqual(lang_code_from_wiktionary_header("Chuvash"), "cv")
        self.assertIsNone(lang_code_from_wiktionary_header("French"))

    def test_detect_script(self):
        self.assertEqual(detect_script("deniz"), "Latin")
        self.assertEqual(detect_script("теңіз"), "Cyrillic")
        self.assertEqual(detect_script("كتاب"), "Arabic")
        self.assertEqual(detect_script("𐰆𐰉"), "Runic")

    def test_empty_result_shape(self):
        class Dummy(BaseFetcher):
            @property
            def source_name(self):
                return "Dummy"

            def fetch(self, word):
                return self.empty_result()

        assert_contract(self, Dummy().fetch("x"), "Dummy")

    def test_make_entry_marks_origin(self):
        class SeedDummy(BaseFetcher):
            is_seed_source = True

            @property
            def source_name(self):
                return "SeedDummy"

            def fetch(self, word):
                r = self.empty_result()
                r["turkic_languages"].append(self.make_entry("kk", "көз", "göz"))
                return r

        entry = SeedDummy().fetch("göz")["turkic_languages"][0]
        self.assertEqual(entry["origin"], "seed")
        self.assertEqual(entry["script"], "Cyrillic")
        self.assertEqual(entry["lang_name"], "Kazakça")


class TestOfflineFetchers(unittest.TestCase):
    """Tohum veriden beslenen toplayıcılar — ağ gerekmez."""

    def test_contract_and_no_exceptions(self):
        for cls in OFFLINE_FETCHERS:
            fetcher = cls()
            for word in ("deniz", "göz", "", "   ", "zzzqx", "a" * 100):
                with self.subTest(fetcher=cls.__name__, word=word):
                    result = fetcher.fetch(word)
                    assert_contract(self, result, cls.__name__)

    def test_seed_sources_are_labelled(self):
        """Tohum kaynaklar adlarında bunu AÇIKÇA belirtmelidir."""
        for cls in OFFLINE_FETCHERS:
            fetcher = cls()
            if getattr(fetcher, "is_seed_source", False):
                self.assertIn("tohum", fetcher.source_name.lower(), cls.__name__)

    def test_known_seed_words_return_data(self):
        self.assertTrue(StarlingFetcher().fetch("göz")["turkic_languages"])
        self.assertTrue(AcademicTurkologyFetcher().fetch("deniz")["turkic_languages"])

    def test_unknown_word_returns_empty(self):
        self.assertEqual(StarlingFetcher().fetch("zzzqx")["turkic_languages"], [])

    def test_donor_fetcher_finds_loanwords(self):
        res = LoanwordDonorEtymologyFetcher().fetch("kitap")
        assert_contract(self, res, "LoanwordDonorEtymology")
        self.assertTrue(res["turkic_languages"] or res["root"]["proto_turkic"])


class TestNetworkFetchersOffline(unittest.TestCase):
    """Ağ toplayıcıları — ağ ERİŞİLEMEZ olduğunda temiz boş sonuç dönmeli."""

    @responses.activate
    def test_all_return_empty_on_network_failure(self):
        network.reset_session()
        responses.add(responses.GET, re.compile(r".*"), status=500)
        for cls in NETWORK_FETCHERS:
            with self.subTest(fetcher=cls.__name__):
                result = cls().fetch("deniz")
                assert_contract(self, result, cls.__name__)

    @responses.activate
    def test_all_survive_malformed_json(self):
        network.reset_session()
        responses.add(responses.GET, re.compile(r".*"), body="}{ bozuk json", status=200)
        for cls in NETWORK_FETCHERS:
            with self.subTest(fetcher=cls.__name__):
                assert_contract(self, cls().fetch("deniz"), cls.__name__)

    @responses.activate
    def test_all_survive_empty_body(self):
        network.reset_session()
        responses.add(responses.GET, re.compile(r".*"), body="", status=200)
        for cls in NETWORK_FETCHERS:
            with self.subTest(fetcher=cls.__name__):
                assert_contract(self, cls().fetch("deniz"), cls.__name__)


class TestTdkFetchers(unittest.TestCase):
    @responses.activate
    def test_tdk_gts_parses_real_response(self):
        """TDK GTS gerçek yanıtından tanım çıkarılmalıdır.

        Regresyon: kod ``anlamlarList`` arıyordu, TDK ``anlamlarListe``
        döndürüyor. Tek harflik bu hata TDK katmanını tamamen susturuyordu.
        """
        network.reset_session()
        responses.add(
            responses.GET,
            re.compile(r"https://sozluk\.gov\.tr/gts.*"),
            body=load_http_fixture("tdk_gts_deniz.json"),
            content_type="application/json",
        )
        res = TdkFetcher().fetch("deniz")
        assert_contract(self, res, "TdkFetcher")
        self.assertTrue(res["turkic_languages"], "TDK tanım döndürmedi")
        self.assertIn("kabuğ", res["root"]["meaning"].lower())

    @responses.activate
    def test_tdk_derleme_parses(self):
        network.reset_session()
        responses.add(
            responses.GET,
            re.compile(r"https://sozluk\.gov\.tr/derleme.*"),
            body=load_http_fixture("tdk_derleme_deniz.json"),
            content_type="application/json",
        )
        res = TdkDerlemeFetcher().fetch("deniz")
        assert_contract(self, res, "TdkDerleme")

    @responses.activate
    def test_tdk_tarama_handles_not_found(self):
        """TDK 'Sonuç bulunamadı' hatasını bulgu sanmamalıdır."""
        network.reset_session()
        responses.add(
            responses.GET,
            re.compile(r"https://sozluk\.gov\.tr/tarama.*"),
            body=load_http_fixture("tdk_tarama_deniz.json"),
            content_type="application/json",
        )
        res = TdkTaramaFetcher().fetch("deniz")
        assert_contract(self, res, "TdkTarama")
        self.assertEqual(res["turkic_languages"], [])


class TestWiktionaryFetchers(unittest.TestCase):
    def test_word_page_parser_extracts_turkic_sections(self):
        """İngilizce Wiktionary kelime sayfası ayrıştırıcısı ÇALIŞMALIDIR.

        Regresyon: dil-adı eşleme hatası nedeniyle bu ayrıştırıcı hiçbir
        zaman sonuç üretmiyordu.
        """
        wikitext = (
            "==Turkish==\n===Etymology===\nFrom Proto-Turkic.\n"
            "===Noun===\n# [[eye]]\n"
            "==Kazakh==\n===Noun===\n# [[eye]], [[vision]]\n"
            "==French==\n===Noun===\n# [[oeil]]\n"
        )
        result = {"root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
                  "turkic_languages": []}
        WiktionaryFetcher()._parse_word_page(wikitext, "göz", result)
        codes = {e["lang_code"] for e in result["turkic_languages"]}
        self.assertIn("tr", codes)
        self.assertIn("kk", codes)
        self.assertNotIn("fr", codes)
        self.assertTrue(all(e["meaning"] for e in result["turkic_languages"]))

    def test_subsection_headings_do_not_split_language_sections(self):
        """`===Noun===` gibi ALT başlıklar dil bölümünü bölmemelidir."""
        wikitext = "==Turkish==\n===Etymology===\nx\n===Noun===\n# [[eye]]\n"
        result = {"root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
                  "turkic_languages": []}
        WiktionaryFetcher()._parse_word_page(wikitext, "göz", result)
        self.assertEqual(result["turkic_languages"][0]["meaning"], "eye")

    @responses.activate
    def test_wiktionary_full_fetch(self):
        network.reset_session()
        responses.add(
            responses.GET,
            re.compile(r"https://en\.wiktionary\.org/w/api\.php.*"),
            body=load_http_fixture("wiktionary_en_deniz.json"),
            content_type="application/json",
        )
        res = WiktionaryFetcher().fetch("deniz")
        assert_contract(self, res, "Wiktionary")

    @responses.activate
    def test_wiktextract_fetch(self):
        network.reset_session()
        responses.add(
            responses.GET,
            re.compile(r".*rest_v1/page/definition.*"),
            body=load_http_fixture("wiktextract_göz.json"),
            content_type="application/json",
        )
        res = WiktextractFetcher().fetch("göz")
        assert_contract(self, res, "Wiktextract")


class TestEtimolojiTurkceFetcher(unittest.TestCase):
    @responses.activate
    def test_extracts_dated_attestation(self):
        """Tarihli ilk tanıklama çıkarılmalıdır — A-HVP kronolojisinin girdisi."""
        network.reset_session()
        responses.add(
            responses.GET,
            re.compile(r"https://www\.etimolojiturkce\.com/kelime/.*"),
            body=load_http_fixture("etimolojiturkce_deniz.html"),
            content_type="text/html",
        )
        res = EtimolojiTurkceFetcher().fetch("deniz")
        assert_contract(self, res, "EtimolojiTurkce")
        att = res.get("first_attestation")
        self.assertIsNotNone(att, "tanıklama çıkarılamadı")
        self.assertEqual(att["year"], 1070)
        self.assertIn("Divan", att["source"])

    @responses.activate
    def test_turkish_characters_not_mojibake(self):
        """Sunucu charset bildirmese de Türkçe karakterler bozulmamalıdır.

        Regresyon: `Content-Type: text/html` (charset yok) -> requests
        ISO-8859-1 varsayıyor, 'eş' -> 'eÅ' oluyordu.
        """
        network.reset_session()
        responses.add(
            responses.GET,
            re.compile(r"https://www\.etimolojiturkce\.com/kelime/.*"),
            body=load_http_fixture("etimolojiturkce_deniz.html"),
            content_type="text/html",
        )
        res = EtimolojiTurkceFetcher().fetch("deniz")
        blob = str(res)
        self.assertNotIn("Å", blob)
        self.assertNotIn("Ã¼", blob)


class TestFetcherPortfolio(unittest.TestCase):
    def test_default_portfolio_is_healthy(self):
        fetchers = default_fetchers()
        self.assertGreaterEqual(len(fetchers), 15)
        names = [f.source_name for f in fetchers]
        self.assertEqual(len(names), len(set(names)), "yinelenen kaynak adı")

    def test_dead_sources_are_removed(self):
        """Ölü uç noktalar portföyde OLMAMALIDIR (Glosbe 404, TDK TTAS/Kişi 404)."""
        blob = " ".join(f.source_name for f in default_fetchers()).lower()
        self.assertNotIn("glosbe", blob)
        self.assertNotIn("dergipark", blob)

    def test_seed_and_live_are_distinguishable(self):
        fetchers = default_fetchers()
        seed = [f for f in fetchers if getattr(f, "is_seed_source", False)]
        live = [f for f in fetchers if not getattr(f, "is_seed_source", False)]
        self.assertTrue(seed, "tohum kaynak yok")
        self.assertTrue(live, "canlı kaynak yok")


if __name__ == "__main__":
    unittest.main()
