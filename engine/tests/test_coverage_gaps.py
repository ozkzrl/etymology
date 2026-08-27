"""
Kalan Kapsam Boşlukları İçin Testler

CLI çıktı biçimlendirme, PDF tarama, donör sözlüğü canlı yolu, türev ağı
doğrulaması ve fetcher ayrıştırıcılarının derin yolları.
"""
from __future__ import annotations

import io
import json
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import responses

from engine.cli import print_finding_formatted
from engine.db.cldf_importer import CldfImporter
from engine.fetchers.academic_turkology import AcademicTurkologyFetcher
from engine.fetchers.archive_org import ArchiveOrgFetcher
from engine.fetchers.isam_ansiklopedi import IsamAnsiklopediFetcher
from engine.fetchers.local_pdf_books import LocalPdfBooksFetcher, extract_pdf_text
from engine.fetchers.multilang_wiktionary import MultiLangWiktionaryFetcher
from engine.fetchers.osmanlica_lugat import OsmanlicaLugatFetcher
from engine.fetchers.tdk_nisanyan import NisanyanFetcher
from engine.nlp.derivation_network import DerivationNetworkBuilder
from engine.nlp.donor_etymology_database import (
    DeepDonorEtymologyDatabase,
    _detect_donor_language,
)
from engine.nlp.donor_lexicon import DonorLexicon
from engine.nlp.phonological_feature_engine import PhonologicalFeatureEngine, to_ipa
from engine.tests.conftest import load_http_fixture
from engine.utils import network

FIXTURES = Path(__file__).parent / "fixtures"


def full_finding():
    return {
        "query_word": "göz",
        "morphology": "Kök: göz",
        "from_cache": False,
        "root": {"proto_turkic": "*köŕ", "meaning": "görme organı",
                 "reconstruction_notes": "Lir-Şaz rotasizmi"},
        "turkic_languages": [
            {"lang_code": "tr", "lang_name": "Türkiye Türkçesi", "word": "göz",
             "meaning": "göz", "script": "Latin", "phonetic_shift": "—", "origin": "live"},
            {"lang_code": "kk", "lang_name": "Kazakça", "word": "көз", "meaning": "göz",
             "script": "Cyrillic", "phonetic_shift": "k~g", "origin": "seed",
             "latin_transliteration": "köz"},
            {"lang_code": "donor", "lang_name": "Kaynak Dil", "word": "x",
             "meaning": "y", "script": "Original"},
        ],
        "sources": ["TDK", "Wiktionary"],
        "timeline": ["1074 DLT: köz"],
        "related_cognates": ["көз", "күз"],
        "graph_database": {"node_count": 4, "edge_count": 3,
                           "graph_data": {"nodes": [], "edges": []}},
        "nlp_analysis": {
            "loanword_classification": {
                "classification": "Asli Öz Türkçe",
                "probabilities": {"p_native_turkic": 0.9, "p_arabic_persian": 0.05,
                                  "p_greek_latin": 0.02, "p_western": 0.03},
                "phonotactic_violations": [],
            },
            "cognate_distribution": {"spreading_ratio": 0.4, "present_dialects_count": 8,
                                     "assessment": "geniş", "alignment_score": 0.9,
                                     "evidence_available": True, "total_language_count": 25},
            "reconstruction": {"reconstructed_root": "*köŕ", "confidence": 0.85,
                               "reconstruction_notes": "n", "is_reconstructible": True,
                               "evidence_available": True},
            "donor_matching": {"found_match": False, "donor_language": None},
            "proven_hypothesis": {
                "hypothesis_type": "Asli Proto-Türkçe kök",
                "origin_form": "*köŕ", "donor_language": "Proto-Türkçe",
                "proof_summary": "kanıt", "confidence_score": 0.72,
                "validation_report": {
                    "badge": "🟢 DOĞRULANDI", "score_percentage": "%72",
                    "final_confidence_score": 0.72, "evidence_coverage": 0.85,
                    "stage_score": 0.85, "contributing_stages": ["phonetic"],
                    "missing_evidence": ["semantic"],
                    "stage_breakdown": {
                        "stage1_phonetic_chain": {"is_valid": True, "matched_rules": ["k~g"],
                                                  "violations": [], "evidence_available": True},
                        "stage2_time_lock": {"is_valid": True, "evidence_available": True},
                        "stage3_semantic_drift": {"is_valid": None, "evidence_available": False},
                        "stage4_cognate_triangulation": {"is_valid": True, "evidence_available": True,
                                                         "sample_cognates": ["көз"]},
                    },
                    "rejection_reasons": [],
                },
            },
            "unattested_word_reconstruction": {"hypothesis_available": False},
            "lingpy_alignment": {"aligned_seq1": "köŕ", "aligned_seq2": "göz",
                                 "phonetic_similarity": 0.8, "sound_class_seq1": "KUS",
                                 "sound_class_seq2": "KUS"},
            "diachronic_semantic_drift": {"evidence_available": False, "is_plausible": None},
            "induced_sound_laws": {"evidence_available": True,
                                   "induced_rules": [{"rule_id": "INITIAL_K_G",
                                                      "pattern": "#k -> #g",
                                                      "description": "d", "confidence": 0.9}]},
            "loanword_detection": {"verdict": "native", "confidence": 0.9,
                                   "classification": "Asli Öz Türkçe",
                                   "rationale": ["Katman 1: ihlal yok"], "layers": {}},
            "cognate_clusters": {"evidence_available": True, "cluster_count": 1,
                                 "largest_cluster_size": 8, "clusters": []},
            "historical_morphology": {"root": "gö", "depth": 1,
                                      "derivation_path": "gö + -z", "layers": []},
        },
        "diagnostics": {"stage_timings_ms": {"total": 12}, "sources": {},
                        "http": {}, "variants_used": ["göz"], "live_source_count": 1},
    }


class TestCliFormatting(unittest.TestCase):
    """`print_finding_formatted` daha önce hiç çalıştırılmamıştı."""

    def _render(self, finding):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_finding_formatted(finding)
        return buf.getvalue()

    def test_renders_full_finding(self):
        out = self._render(full_finding())
        self.assertIn("göz", out)
        self.assertIn("*köŕ", out)

    def test_renders_minimal_finding(self):
        out = self._render({"query_word": "x", "root": {}, "turkic_languages": [],
                            "sources": [], "nlp_analysis": {}})
        self.assertIn("X", out)  # başlık büyük harfe çevrilir

    def test_renders_without_hypothesis(self):
        f = full_finding()
        f["nlp_analysis"]["proven_hypothesis"] = None
        self.assertTrue(self._render(f))

    def test_renders_with_rejections(self):
        f = full_finding()
        f["nlp_analysis"]["proven_hypothesis"]["validation_report"]["rejection_reasons"] = [
            "ANAKRONİZM: kaynak dil teması sonradır"
        ]
        self.assertIn("ANAKRONİZM", self._render(f))

    def test_renders_with_ai_enrichment(self):
        f = full_finding()
        f["ai_agent_enrichment"] = "Yapay zekâ sentezi metni."
        f["discovered_web_sources"] = [{"title": "T", "url": "https://x", "snippet": "s"}]
        out = self._render(f)
        self.assertIn("sentezi", out)

    def test_renders_cached_finding(self):
        f = full_finding()
        f["from_cache"] = True
        self.assertTrue(self._render(f))


class TestPdfScanning(unittest.TestCase):
    """Gerçek PDF tam metin taraması (eski sürüm hiç PDF okumuyordu)."""

    def test_extracts_text_from_real_pdf(self):
        pdf = FIXTURES / "test_turkoloji.pdf"
        self.assertTrue(pdf.exists(), "test PDF fixture yok")
        text = extract_pdf_text(pdf)
        self.assertIn("deniz", text.lower())

    def test_fetcher_finds_word_in_pdf(self, ):
        fetcher = LocalPdfBooksFetcher(books_dir=FIXTURES)
        self.assertFalse(fetcher.is_seed_source, "PDF varken tohum kaynak sayılmamalı")
        res = fetcher.fetch("deniz")
        live = [e for e in res["turkic_languages"] if e.get("origin") == "live"]
        self.assertTrue(live)
        self.assertIn("Bağlam", live[0]["meaning"])

    def test_missing_word_in_pdf(self):
        res = LocalPdfBooksFetcher(books_dir=FIXTURES).fetch("zzzqxwv")
        self.assertEqual([e for e in res["turkic_languages"] if e.get("origin") == "live"], [])

    def test_no_books_dir_falls_back_to_seed(self, ):
        fetcher = LocalPdfBooksFetcher(books_dir=Path("/nonexistent-dir-xyz"))
        self.assertTrue(fetcher.is_seed_source)
        self.assertIn("tohum", fetcher.source_name)

    def test_unreadable_pdf_is_handled(self, ):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bozuk.pdf"
            bad.write_bytes(b"bu bir PDF degil")
            self.assertEqual(extract_pdf_text(bad), "")


class TestDonorEtymologyDatabase(unittest.TestCase):
    def test_seed_lookup_is_network_free(self):
        """`lookup()` varsayılan olarak AĞA ÇIKMAMALIDIR.

        Regresyon: her çağrıda canlı Wiktionary sorgusu yapıyordu; tek
        aramada 4 kez çağrıldığı için 'saf NLP' katmanı 4 istek atıyordu.
        """
        db = DeepDonorEtymologyDatabase()
        self.assertIsNotNone(db.lookup("kitap"))
        self.assertIsNone(db.lookup("zzzqx"))

    def test_live_lookup_requires_opt_in(self):
        db = DeepDonorEtymologyDatabase(allow_live=True)
        with mock.patch(
            "engine.llm.advanced_tools.tool_wiktionary_multilingual_api",
            return_value={"raw_found": True, "api_summary": ["From Arabic kitāb"]},
        ):
            res = db.lookup("zzzqx")
        self.assertIsNotNone(res)
        self.assertEqual(res["donor_language"], "Arapça")

    def test_live_lookup_without_donor_language_returns_none(self):
        db = DeepDonorEtymologyDatabase(allow_live=True)
        with mock.patch(
            "engine.llm.advanced_tools.tool_wiktionary_multilingual_api",
            return_value={"raw_found": True, "api_summary": ["belirsiz metin"]},
        ):
            self.assertIsNone(db.lookup("zzzqx"))

    def test_live_lookup_handles_exception(self):
        db = DeepDonorEtymologyDatabase(allow_live=True)
        with mock.patch(
            "engine.llm.advanced_tools.tool_wiktionary_multilingual_api",
            side_effect=RuntimeError("boom"),
        ):
            self.assertIsNone(db.lookup("zzzqx"))

    def test_donor_language_detection(self):
        self.assertEqual(_detect_donor_language("From Arabic root"), "Arapça")
        self.assertEqual(_detect_donor_language("Fransızca kökenli"), "Fransızca")
        self.assertIsNone(_detect_donor_language("belirsiz"))

    def test_empty_word(self):
        self.assertIsNone(DeepDonorEtymologyDatabase().lookup(""))


class TestDonorLexiconLive(unittest.TestCase):
    @responses.activate
    def test_live_search_aggregates_languages(self):
        network.reset_session()
        responses.add(
            responses.GET, re.compile(r"https://ar\.wiktionary\.org/.*"),
            json={"query": {"pages": {"1": {"extract": "كتاب: yazılan şey"}}}}, status=200,
        )
        responses.add(responses.GET, re.compile(r".*wiktionary\.org.*"),
                      json={"query": {"pages": {"1": {"missing": ""}}}}, status=200)
        out = DonorLexicon().search_live("kitap")
        self.assertTrue(any(r["donor_language"] == "Arapça" for r in out))

    @responses.activate
    def test_live_search_survives_failures(self):
        network.reset_session()
        responses.add(responses.GET, re.compile(r".*"), status=500)
        self.assertEqual(DonorLexicon().search_live("kitap"), [])

    def test_live_search_empty_word(self):
        self.assertEqual(DonorLexicon().search_live(""), [])

    @responses.activate
    def test_malformed_json_handled(self):
        network.reset_session()
        responses.add(responses.GET, re.compile(r".*"), body="}{", status=200)
        self.assertEqual(DonorLexicon().search_live("kitap"), [])

    def test_candidate_forms_are_matched(self):
        out = DonorLexicon().nearest_neighbours("kitap", {"ar": ["kitab", "kitāb"]})
        self.assertTrue(any(r["origin"] == "live" for r in out))


class TestDerivationNetworkVerification(unittest.TestCase):
    def test_verified_build_uses_validator(self):
        class FakeValidator:
            def fetch(self, word):
                found = word in {"gözlük", "gözcü"}
                return {
                    "root": {"meaning": "test anlamı" if found else ""},
                    "turkic_languages": [{"meaning": "x"}] if found else [],
                }

        res = DerivationNetworkBuilder(validator=FakeValidator()).build("göz")
        words = {d["word"] for d in res["derivations"]}
        self.assertEqual(words, {"gözlük", "gözcü"})
        self.assertTrue(all(d["verified"] for d in res["derivations"]))

    def test_validator_exception_is_isolated(self):
        class Boom:
            def fetch(self, word):
                raise RuntimeError("x")

        res = DerivationNetworkBuilder(validator=Boom()).build("göz")
        self.assertEqual(res["confirmed_count"], 0)


class TestPhonologicalBackends(unittest.TestCase):
    def test_ipa_conversion(self):
        self.assertTrue(to_ipa("göz"))
        self.assertEqual(to_ipa(""), "")

    def test_feature_vector_for_unknown_symbol(self):
        self.assertIsInstance(PhonologicalFeatureEngine().get_feature_vector("§"), list)

    def test_identical_chars_zero_distance(self):
        self.assertEqual(PhonologicalFeatureEngine().articulatory_distance("k", "k"), 0.0)

    def test_fallback_distance_path(self):
        e = PhonologicalFeatureEngine()
        dist, norm = e._fallback_distance("göz", "köz")
        self.assertGreaterEqual(dist, 0.0)
        self.assertLessEqual(norm, 1.0)

    def test_backend_is_reported(self):
        self.assertIn(PhonologicalFeatureEngine().backend, ("panphon", "fallback"))


class TestFetcherDeepPaths(unittest.TestCase):
    """Fetcher ayrıştırıcılarının kayıtlı gerçek yanıtlarla derin yolları."""

    @responses.activate
    def test_nisanyan_parses_payload(self):
        network.reset_session()
        responses.add(
            responses.GET, re.compile(r".*nisanyansozluk\.com/kelime/.*"),
            body=load_http_fixture("nisanyan_deniz.html"), status=200, content_type="text/html",
        )
        res = NisanyanFetcher().fetch("deniz")
        self.assertIn("root", res)

    @responses.activate
    def test_archive_org_parses(self):
        network.reset_session()
        responses.add(
            responses.GET, re.compile(r".*archive\.org.*"),
            body=load_http_fixture("archive_deniz.json"), status=200,
            content_type="application/json",
        )
        self.assertIn("root", ArchiveOrgFetcher().fetch("deniz"))

    @responses.activate
    def test_multilang_wiktionary_parses_definition(self):
        network.reset_session()
        responses.add(
            responses.GET, re.compile(r".*wiktionary\.org/w/api\.php.*"),
            json={"parse": {"wikitext": {"*": "==Kazakça==\n# [[көз]] anlamı burada\n" * 3}}},
            status=200,
        )
        res = MultiLangWiktionaryFetcher().fetch("göz")
        self.assertTrue(res["turkic_languages"])

    @responses.activate
    def test_isam_and_osmanlica_paths(self):
        network.reset_session()
        responses.add(responses.GET, re.compile(r".*"),
                      body="<html><p>deniz hakkında madde metni</p></html>",
                      status=200, content_type="text/html")
        for cls in (IsamAnsiklopediFetcher, OsmanlicaLugatFetcher):
            self.assertIn("root", cls().fetch("deniz"))

    @responses.activate
    def test_academic_turkology_live_path(self):
        network.reset_session()
        responses.add(responses.GET, re.compile(r".*sozluk\.gov\.tr.*"),
                      json=[{"terim": "deniz", "anlam": "su kütlesi"}], status=200)
        self.assertIn("root", AcademicTurkologyFetcher().fetch("deniz"))


class TestCldfImporterPaths(unittest.TestCase):
    def test_metadata_based_table_discovery(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "forms.csv").write_text("ID,Language_ID,Form\nf1,tur,kitap\n", encoding="utf-8")
            (root / "meta.json").write_text(
                json.dumps({"tables": [{"url": "forms.csv"}]}), encoding="utf-8"
            )
            self.assertTrue(CldfImporter(root).read_forms())

    def test_write_seed_creates_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            imp = CldfImporter(d)
            with mock.patch("engine.db.cldf_importer.SEED_DIR", Path(d)):
                out = imp.write_seed({"kitap": {"donor_lang": "Arapça"}}, "x.json")
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["_provenance"]["entry_count"], 1)

    def test_skips_rows_with_missing_forms(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "forms.csv").write_text("ID,Language_ID,Form\nf1,tur,kitap\n", encoding="utf-8")
            (root / "borrowings.csv").write_text(
                "ID,Target_Form_ID,Source_Form_ID\nb1,f1,YOK\n", encoding="utf-8"
            )
            self.assertEqual(CldfImporter(root).to_donor_entries("tur"), {})


if __name__ == "__main__":
    unittest.main()
