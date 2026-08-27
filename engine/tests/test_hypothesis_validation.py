"""
A-HVP Hakem Protokolü Birim Testleri

Bu testlerin merkezinde tek bir ilke var: **KANIT YOKSA PUAN DA YOK**.
Önceki sürümde dört aşamanın dördü de kanıt yokluğunda cömert varsayılan
puanlar veriyor, uydurma bir kelime %96 "🟢 VALIDATED" alabiliyordu.
"""
import unittest

from engine.nlp.hypothesis_validation_protocol import (
    ChronologicalTimeLock,
    CrossCognateTriangulator,
    HypothesisValidationProtocol,
    PhoneticChainVerifier,
    SemanticDriftEvaluator,
)


def make_entries(pairs, origin="live", source="TestSource"):
    """Test için gerçekçi dil kaydı listesi üretir."""
    return [
        {"lang_code": code, "word": form, "source": src, "origin": origin}
        for code, form, src in ((c, f, source) for c, f in pairs)
    ]


class TestHypothesisValidationProtocol(unittest.TestCase):
    def setUp(self):
        self.protocol = HypothesisValidationProtocol()
        self.time_lock = ChronologicalTimeLock()
        self.phonetic_verifier = PhoneticChainVerifier()
        self.semantic_evaluator = SemanticDriftEvaluator()
        self.triangulator = CrossCognateTriangulator()
        self.goz_entries = make_entries([
            ("tr", "göz"), ("az", "göz"), ("kk", "көз"), ("tt", "күз"),
            ("cv", "куҫ"), ("ky", "көз"), ("otk", "köz"), ("ba", "күҙ"),
        ])

    # --- Kanıt kapsamı ---------------------------------------------------

    def test_fabricated_word_gets_insufficient_evidence(self):
        """Uydurma kelime, kanıt olmadan DOĞRULANMAMALIDIR.

        Regresyon: 'zzzqx' eskiden %96 '🟢 VALIDATED (Bilimsel Hakem Onaylı)'
        alıyordu.
        """
        report = self.protocol.validate_hypothesis(
            "zzzqx",
            {"origin_form": "*zzzqx", "donor_language": "Proto-Türkçe",
             "historical_meaning": "", "modern_meaning": ""},
            attestation_record=None,
            turkic_entries=[],
        )
        self.assertEqual(report["status_code"], "INSUFFICIENT_EVIDENCE")
        self.assertLess(report["evidence_coverage"], 0.5)
        self.assertNotIn("VALIDATED", report["badge"])

    def test_missing_evidence_is_reported_not_scored(self):
        """Kanıt üretemeyen aşamalar puana KATILMAMALI, açıkça raporlanmalıdır."""
        report = self.protocol.validate_hypothesis(
            "zzzqx",
            {"origin_form": "*zzzqx", "donor_language": "Proto-Türkçe"},
            attestation_record=None,
            turkic_entries=[],
        )
        self.assertIn("chronology", report["missing_evidence"])
        self.assertIn("triangulation", report["missing_evidence"])
        self.assertEqual(
            report["stage_breakdown"]["stage2_time_lock"]["evidence_available"], False
        )
        self.assertIsNone(report["stage_breakdown"]["stage2_time_lock"]["score"])

    def test_well_attested_etymology_scores_high(self):
        """Gerçek, çok tanıklı bir etimoloji yüksek skor ve kapsam almalıdır."""
        report = self.protocol.validate_hypothesis(
            "göz",
            {"origin_form": "*köŕ", "donor_language": "Proto-Türkçe",
             "historical_meaning": "göz", "modern_meaning": "göz"},
            attestation_record={"verified": True, "first_attestation_year": 1074},
            turkic_entries=self.goz_entries,
        )
        self.assertIn(report["status_code"], ("VALIDATED", "NEEDS_REVIEW"))
        self.assertGreaterEqual(report["evidence_coverage"], 0.80)
        self.assertGreater(report["final_confidence_score"], 0.60)
        self.assertTrue(report["stage_breakdown"]["stage1_phonetic_chain"]["is_valid"])

    # --- Aşama 2: anakronizm ---------------------------------------------

    def test_anachronism_is_rejected(self):
        """Kaynak dil teması tanıklamadan SONRAYSA hipotez reddedilmelidir."""
        report = self.protocol.validate_hypothesis(
            "su",
            {"origin_form": "sous", "donor_language": "Fransızca",
             "historical_meaning": "su", "modern_meaning": "su"},
            attestation_record={"verified": True, "first_attestation_year": 735},
            turkic_entries=self.goz_entries,
        )
        self.assertEqual(report["status_code"], "REJECTED")
        self.assertFalse(report["stage_breakdown"]["stage2_time_lock"]["is_valid"])
        self.assertTrue(any("ANAKRONİZM" in r for r in report["rejection_reasons"]))

    def test_time_lock_without_dates_yields_no_evidence(self):
        """Tarih bilinmiyorsa aşama 1.0 DEĞİL, 'kanıt yok' döndürmelidir."""
        res = self.time_lock.verify("", None)
        self.assertFalse(res["evidence_available"])
        self.assertIsNone(res["score"])
        self.assertIsNone(res["is_valid"])

    def test_year_parser_ignores_page_numbers(self):
        """Sayfa ve cilt numaraları yıl sanılmamalıdır."""
        self.assertIsNone(self.time_lock.parse_year_or_century("Clauson EDPT s. 456"))
        self.assertIsNone(self.time_lock.parse_year_or_century("cilt 2 sayfa 130"))
        self.assertEqual(self.time_lock.parse_year_or_century("735 yılı Orhun"), 735)
        self.assertEqual(self.time_lock.parse_year_or_century("11. yüzyıl"), 1050)
        self.assertEqual(self.time_lock.parse_year_or_century("Cumhuriyet dönemi 1935"), 1935)

    def test_donor_contact_periods(self):
        """Donör dillerin temas dönemleri makul sırada olmalıdır."""
        self.assertLess(
            self.time_lock.donor_contact_year("Arapça"),
            self.time_lock.donor_contact_year("Fransızca"),
        )
        self.assertIsNone(self.time_lock.donor_contact_year("Klingonca"))

    # --- Aşama 1: fonetik zincir -----------------------------------------

    def test_broken_phonetic_chain_is_invalid(self):
        """Alâkasız biçimler arasında geçerli ses zinciri bulunmamalıdır."""
        result = self.phonetic_verifier.verify("xyzq", "göz")
        self.assertTrue(result["evidence_available"])
        self.assertFalse(result["is_valid"])
        self.assertLess(result["score"], 0.50)
        self.assertTrue(result["violations"])

    def test_regular_correspondence_is_valid(self):
        """Düzenli ses denklikleri (*köŕ ~ göz) geçerli sayılmalıdır."""
        result = self.phonetic_verifier.verify("*köŕ", "göz")
        self.assertTrue(result["is_valid"])
        self.assertGreater(result["score"], 0.55)

    def test_phonetic_verifier_without_input_has_no_evidence(self):
        res = self.phonetic_verifier.verify("", "")
        self.assertFalse(res["evidence_available"])
        self.assertIsNone(res["score"])

    # --- Aşama 4: triangulation ------------------------------------------

    def test_triangulation_uses_real_entries_only(self):
        """Aşama 4 GERÇEK kayıtları saymalı, üretilmiş varyantları değil.

        Regresyon: eski sürüm kendi ürettiği transkripsiyonları sayıp
        her kelimeye sabit 0.95 veriyordu.
        """
        empty = self.triangulator.verify("zzzqx", [])
        self.assertFalse(empty["evidence_available"])
        self.assertIsNone(empty["score"])

        rich = self.triangulator.verify("göz", self.goz_entries)
        self.assertTrue(rich["evidence_available"])
        self.assertEqual(rich["cognate_count"], 8)
        self.assertGreater(rich["score"], 0.5)

    def test_triangulation_ignores_pseudo_language_codes(self):
        """'donor' gibi sözde kodlar lehçe sayısına dâhil edilmemelidir."""
        entries = [
            {"lang_code": "tr", "word": "göz", "source": "TDK", "origin": "live"},
            {"lang_code": "donor", "word": "X", "source": "TDK", "origin": "live"},
            {"lang_code": "ai", "word": "Y", "source": "TDK", "origin": "live"},
        ]
        res = self.triangulator.verify("göz", entries)
        self.assertEqual(res["cognate_count"], 1)

    # --- Aşama 3: semantik -----------------------------------------------

    def test_semantic_stage_without_data_has_no_evidence(self):
        res = self.semantic_evaluator.verify("", "")
        self.assertFalse(res["evidence_available"])
        self.assertIsNone(res["score"])


if __name__ == "__main__":
    unittest.main()
