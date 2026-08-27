"""
Çözülmemiş Kelimeler İçin Otonom Etimoloji Rekonstrüksiyon Mimarisi Birim Testleri
(Jenerik Ek Soyma, Tahminleyici Proto-Kök Türetimi ve İnatçı A-HVP Hipotez Kurma)
Sıfır kelime bazlı hardcode içerir.
"""
import unittest

from engine.nlp.iterative_hypothesis_prover import IterativeHypothesisProver
from engine.nlp.predictive_reconstructor import PredictiveReconstructor
from engine.nlp.unsupervised_morpheme_segmenter import UnsupervisedMorphemeSegmenter


class TestUnattestedEtymologyReconstruction(unittest.TestCase):

    def setUp(self):
        self.segmenter = UnsupervisedMorphemeSegmenter()
        self.reconstructor = PredictiveReconstructor()
        self.prover = IterativeHypothesisProver()

    def test_unsupervised_morpheme_segmentation(self):
        """Kelimelerin yapım/çekim eklerini hiçbir hardcode kelime olmadan jenerik soyma testi"""
        res = self.segmenter.segment_morphemes("yağmurluk")
        self.assertTrue(res["is_segmented"])
        self.assertIn("-luk", res["affixes"])

    def test_reconstruction_requires_cognate_witnesses(self):
        """Akraba tanığı olmadan ata biçim ÜRETİLMEMELİDİR.

        Eskiden her kelimeye körlemesine k->g / t->d kuralları uygulanıp
        sabit 0.88 güven skoruyla bir *proto-form uyduruluyordu.
        """
        res = self.reconstructor.reconstruct_unattested_proto_form("korak")
        self.assertFalse(res["evidence_available"])
        self.assertEqual(res["reconstructed_proto_form"], "")
        self.assertIsNone(res["reconstruction_confidence"])

    def test_predictive_proto_form_from_real_cognates(self):
        """Gerçek akraba tanıklarından karşılaştırmalı yöntemle ata biçim türetimi."""
        cognates = [
            {"lang_code": "tr", "word": "göz"},
            {"lang_code": "kk", "word": "көз"},
            {"lang_code": "cv", "word": "куҫ"},
            {"lang_code": "tt", "word": "күз"},
        ]
        res = self.reconstructor.reconstruct_unattested_proto_form("göz", cognates)
        self.assertTrue(res["evidence_available"])
        # Lir-Şaz rotasizmi (z ~ r) ve söz başı ötümlülük (g ~ k) uygulanmalı
        self.assertEqual(res["reconstructed_proto_form"], "*köŕ")
        self.assertGreater(res["reconstruction_confidence"], 0.5)
        self.assertGreaterEqual(res["witness_count"], 3)

    def test_no_hypothesis_without_evidence(self):
        """Kanıt yoksa hipotez ÜRETİLMEMELİDİR.

        Regresyon: eski sürüm her kelimeye sabit 0.82/0.88 güvenle bir
        '*<kelime>' Proto-Türkçe kökü uyduruyordu.
        """
        res = self.prover.prove_unattested_word("kurtarılmak")
        self.assertIn("hypothesis_available", res)
        if not res["hypothesis_available"]:
            self.assertIsNone(res["proven_hypothesis"])
            self.assertIn("reason", res)

    def test_hypothesis_from_real_cognates(self):
        """Gerçek akraba tanıkları varsa karşılaştırmalı hipotez kurulmalıdır."""
        entries = [
            {"lang_code": "tr", "word": "göz", "source": "TDK", "origin": "live"},
            {"lang_code": "kk", "word": "көз", "source": "Wiktionary", "origin": "live"},
            {"lang_code": "cv", "word": "куҫ", "source": "Starling", "origin": "seed"},
            {"lang_code": "tt", "word": "күз", "source": "Wiktionary", "origin": "live"},
        ]
        res = self.prover.prove_unattested_word("göz", entries)
        self.assertTrue(res["hypothesis_available"])
        hypo = res["proven_hypothesis"]
        self.assertEqual(hypo["origin_form"], "*köŕ")
        self.assertIn("validation_report", hypo)

    def test_compound_neologism_gets_no_proto_root(self):
        """Bileşik neologizme Proto-Türkçe kök ATANMAMALIDIR.

        Regresyon: 'bilgisayar' (1970'ler türetmesi) için '*bilgisayar'
        biçiminde var olmayan bir ata kök üretiliyordu.
        """
        res = self.prover.prove_unattested_word("bilgisayar")
        self.assertTrue(res["hypothesis_available"])
        hypo = res["proven_hypothesis"]
        self.assertTrue(hypo.get("is_modern_derivation"))
        self.assertNotIn("*", hypo["origin_form"])
        self.assertIn("+", hypo["origin_form"])
        self.assertIn("validation_report", hypo)

if __name__ == "__main__":
    unittest.main()
