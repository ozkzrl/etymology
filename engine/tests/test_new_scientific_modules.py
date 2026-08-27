"""
Yeni Hesaplamalı Dilbilim ve Bilimsel NLP Modülleri Birim Testleri
(PanPhon artikülatör vektörleri, CLDF standart aktarıcısı, Wiktextract fetcher)
"""

import unittest

from engine.db.cldf_exporter import CldfExporter
from engine.fetchers.wiktextract_local import WiktextractFetcher
from engine.nlp.cldf_lingpy_aligner import CldfLingPyAligner
from engine.nlp.diachronic_semantic_engine import DiachronicSemanticEngine
from engine.nlp.phonological_feature_engine import PhonologicalFeatureEngine


class TestNewScientificModules(unittest.TestCase):

    def setUp(self):
        self.panphon = PhonologicalFeatureEngine()
        self.lingpy_aligner = CldfLingPyAligner()
        self.semantic_engine = DiachronicSemanticEngine()
        self.cldf_exporter = CldfExporter()
        self.wiktextract = WiktextractFetcher()

    def test_panphon_articulatory_feature_vector(self):
        """Gerçek PanPhon artikülatör özellik vektörleri ve mesafe testi.

        Gerçek PanPhon 24 özellik kullanır; eski sürümdeki elle yazılmış
        taklit matris 21 boyutluydu ve yalnızca 35 karakter içeriyordu.
        """
        v_a = self.panphon.get_feature_vector("a")
        v_e = self.panphon.get_feature_vector("e")
        self.assertEqual(len(v_a), len(v_e))
        self.assertGreaterEqual(len(v_a), 21)

        # İki ünlü birbirine, ünlü-ünsüzden daha yakın olmalı
        dist_ae = self.panphon.articulatory_distance("a", "e")
        dist_ab = self.panphon.articulatory_distance("a", "b")
        self.assertLess(dist_ae, dist_ab)

        # Aynı ses sıfır mesafe
        self.assertEqual(self.panphon.articulatory_distance("a", "a"), 0.0)

        # Düzenli ses denkliği yüksek benzerlik vermeli
        res = self.panphon.sequence_phonological_distance("sub", "suv")
        self.assertTrue(res["evidence_available"])
        self.assertGreater(res["phonetic_similarity"], 0.70)

        # Alâkasız biçimler düşük benzerlik
        unrelated = self.panphon.sequence_phonological_distance("deniz", "araba")
        self.assertLess(unrelated["phonetic_similarity"], 0.40)

    def test_panphon_empty_input_reports_no_evidence(self):
        """Boş girdi tek ve tutarlı bir şema döndürmelidir.

        Eski sürümde boş dal {distance, similarity, matrix}, normal dal
        {phonological_edit_distance, ...} döndürüyor; çağıranlar sessizce
        varsayılanlara düşüyordu.
        """
        res = self.panphon.sequence_phonological_distance("", "")
        self.assertFalse(res["evidence_available"])
        self.assertIsNone(res["phonetic_similarity"])
        self.assertIn("phonological_edit_distance", res)

    def test_cldf_lingpy_sca_dolgopolsky_alignment(self):
        """LingPy SCA Dolgopolsky ses sınıfları hizalaması testi"""
        res = self.lingpy_aligner.align_sequences("teŋiz", "deniz")
        self.assertIn("sound_class_seq1", res)
        self.assertGreater(res["phonetic_similarity"], 0.75)

    def test_cldf_exporter(self):
        """Cross-Linguistic Data Formats (CLDF) standart CSV ve metadata testi"""
        finding = {
            "query_word": "göz",
            "root": {"proto_turkic": "*göŕ", "meaning": "eye"},
            "turkic_languages": [
                {"lang_code": "tr", "word": "göz"},
                {"lang_code": "az", "word": "göz"},
                {"lang_code": "kk", "word": "көз"}
            ]
        }
        exported = self.cldf_exporter.export_to_cldf(finding)
        self.assertIn("cldf_forms_csv", exported)
        self.assertIn("cldf_cognates_csv", exported)
        self.assertIn("form_1", exported["cldf_forms_csv"])

    def test_wiktextract_fetcher_structure(self):
        """Wiktextract / Kaikki fetcher yapısı ve dönen verinin jenerik doğrulama testi"""
        res = self.wiktextract.fetch("deniz")
        self.assertIn("root", res)
        self.assertIn("turkic_languages", res)

if __name__ == "__main__":
    unittest.main()
