"""
İleri Hesaplamalı Etimoloji Modülleri Birim Testleri
(LingPy Hizalama, Diyakronik Vektör Manifoldu, Otomatik Ses Kanunu İndüksiyonu ve Neo4j Graf Şeması)
"""
import unittest

from engine.db.graph_database import GraphDatabaseManager
from engine.nlp.cldf_lingpy_aligner import CldfLingPyAligner
from engine.nlp.diachronic_semantic_engine import DiachronicSemanticEngine
from engine.nlp.sound_law_induction import SoundLawInductionEngine


class TestAdvancedEtymologyModules(unittest.TestCase):

    def setUp(self):
        self.aligner = CldfLingPyAligner()
        self.semantic_engine = DiachronicSemanticEngine()
        self.induction_engine = SoundLawInductionEngine()
        self.graph_db = GraphDatabaseManager()

    def test_cldf_lingpy_sequence_alignment(self):
        """Needleman-Wunsch tabanlı LingPy fonetik dizi hizalama testi"""
        res = self.aligner.align_sequences("*sub", "su")
        self.assertIn("aligned_seq1", res)
        self.assertIn("aligned_seq2", res)
        self.assertGreater(res["phonetic_similarity"], 0.20)
        self.assertTrue(len(res["aligned_pairs"]) > 0)

    def test_diachronic_semantic_vector_trajectory(self):
        """Semantik model yokken aşamanın KANIT ÜRETMEDİĞİNİ bildirmesi gerekir.

        Eskiden veri eksik olduğunda otomatik 0.85 skoru ve is_plausible=True
        veriliyordu; bu, A-HVP toplam skorunun %15'ini bedava puana çeviriyordu.
        """
        res = self.semantic_engine.evaluate_diachronic_trajectory("göz, görme organı", "görüş organı, göz")
        self.assertIn("evidence_available", res)
        if res["evidence_available"]:
            # sentence-transformers kuruluysa gerçek mesafe hesaplanır
            self.assertIsNotNone(res["total_shift_distance"])
            self.assertLessEqual(res["total_shift_distance"], res["theta_threshold"])
        else:
            # Kurulu değilse aşama kanıt üretmez ve karar vermez
            self.assertIsNone(res["is_plausible"])

    def test_semantic_vectors_are_deterministic(self):
        """Aynı metin her çağrıda AYNI vektörü üretmelidir (hash() tohumlaması hatası)."""
        v1, _ = self.semantic_engine.vectorizer.vectorise("deniz, büyük su kütlesi")
        v2, _ = self.semantic_engine.vectorizer.vectorise("deniz, büyük su kütlesi")
        self.assertEqual(v1, v2)

    def test_empty_semantic_input_yields_no_evidence(self):
        """Boş anlam verisi kanıt sayılmamalıdır."""
        res = self.semantic_engine.evaluate_diachronic_trajectory("", "")
        self.assertFalse(res["evidence_available"])
        self.assertIsNone(res["is_plausible"])

    def test_automated_sound_law_induction(self):
        """Akraba sözcük çiftlerinden otonom ses kanunu türetme testi"""
        res = self.induction_engine.induce_sound_law("köz", "göz")
        self.assertTrue(res["has_induced_rule"])
        self.assertTrue(any(r["rule_id"] == "INITIAL_K_G" for r in res["induced_rules"]))

    def test_graph_database_schema_export(self):
        """Neo4j ve Cytoscape uyumlu graf düğüm ve kenar şeması testi"""
        hypothesis = {
            "hypothesis_type": "Asli Öz Türkçe Köken Hipotezi",
            "confidence_score": 0.95,
            "donor_language": "Proto-Türkçe"
        }
        attestations = ["8. yy Orhun Yazıtları (kös)", "11. yy DLT (göz)"]
        cognates = ["görmek", "gözlem", "gözlük"]

        graph = self.graph_db.build_etymology_graph("göz", "*göŕ", hypothesis, attestations, cognates)
        self.assertGreater(graph["node_count"], 3)
        self.assertGreater(graph["edge_count"], 3)
        self.assertIn("elements", graph["cytoscape_format"])

if __name__ == "__main__":
    unittest.main()
