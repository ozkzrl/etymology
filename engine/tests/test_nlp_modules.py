"""
NLP Katmanı Birim Testleri

Daha önce test edilmemiş 10 NLP modülünü ve Faz 6'da eklenen yeni modülleri
kapsar.
"""
from __future__ import annotations

import unittest

from engine.nlp.cognate_alignment import CognateAlignmentEngine
from engine.nlp.cognate_clustering import CognateClusterEngine
from engine.nlp.comparative_reconstruction import ComparativeReconstructor
from engine.nlp.derivation_network import DerivationNetworkBuilder
from engine.nlp.diachronic_semantic_engine import DiachronicSemanticEngine
from engine.nlp.donor_lexicon import DonorLexicon, ipa_distance, levenshtein
from engine.nlp.donor_search import DonorSearchEngine
from engine.nlp.historical_attestation_verifier import HistoricalAttestationVerifier
from engine.nlp.historical_morphology import HistoricalMorphologyAnalyzer
from engine.nlp.iterative_hypothesis_engine import IterativeHypothesisEngine
from engine.nlp.loanword_classifier import LoanwordClassifier
from engine.nlp.loanword_detector import LoanwordDetector
from engine.nlp.neologism_detector import NeologismDetector
from engine.nlp.reconstruction import ProtoTurkicReconstructor
from engine.nlp.sound_law_induction import SoundLawInductionEngine
from engine.nlp.unsupervised_morpheme_segmenter import UnsupervisedMorphemeSegmenter


def entries(pairs, origin="live"):
    return [
        {"lang_code": c, "word": w, "source": f"S{i}", "origin": origin,
         "lang_name": c, "meaning": "test", "script": "Latin"}
        for i, (c, w) in enumerate(pairs)
    ]


GOZ = entries([("tr", "göz"), ("az", "göz"), ("kk", "көз"), ("tt", "күз"),
               ("cv", "куҫ"), ("otk", "köz"), ("ky", "көз"), ("ba", "күҙ")])


class TestComparativeReconstruction(unittest.TestCase):
    def test_produces_correct_proto_forms(self):
        """Karşılaştırmalı yöntem bilinen ata biçimleri üretmelidir."""
        r = ComparativeReconstructor()
        cases = {
            "göz": ("*köŕ", [("tr", "göz"), ("kk", "көз"), ("cv", "куҫ"), ("tt", "күз")]),
            "deniz": ("*teŋiŕ", [("tr", "deniz"), ("kk", "теңіз"), ("cv", "тинӗс"), ("tk", "deňiz")]),
            "yol": ("*jol", [("tr", "yol"), ("kk", "жол"), ("cv", "ҫул"), ("tt", "юл")]),
        }
        for word, (expected, pairs) in cases.items():
            with self.subTest(word=word):
                out = r.reconstruct(word, entries(pairs))
                self.assertEqual(out["reconstructed_root"], expected)

    def test_requires_two_witnesses(self):
        """Tek tanıkla ata biçim ÜRETİLMEMELİDİR."""
        r = ComparativeReconstructor()
        out = r.reconstruct("göz", entries([("tr", "göz")]))
        self.assertFalse(out["evidence_available"])
        self.assertEqual(out["reconstructed_root"], "")

    def test_confidence_grows_with_evidence(self):
        r = ComparativeReconstructor()
        few = r.reconstruct("göz", entries([("tr", "göz"), ("kk", "көз")]))
        many = r.reconstruct("göz", GOZ)
        self.assertGreater(many["confidence"], few["confidence"])

    def test_branch_diversity_is_reported(self):
        out = ComparativeReconstructor().reconstruct("göz", GOZ)
        self.assertGreaterEqual(out["branch_count"], 3)
        self.assertIn("oghur", out["branches"])

    def test_empty_word(self):
        out = ComparativeReconstructor().reconstruct("", GOZ)
        self.assertFalse(out["evidence_available"])

    def test_facade_rejects_non_turkic_initial(self):
        out = ProtoTurkicReconstructor().reconstruct_proto_form("fistan", GOZ)
        self.assertFalse(out["is_reconstructible"])


class TestCognateAlignment(unittest.TestCase):
    def test_spreading_uses_real_language_count(self):
        """Yayılım, koda gömülü 25 yerine gerçek dil sayısına bölünmelidir."""
        res = CognateAlignmentEngine().evaluate_cognate_distribution("göz", GOZ)
        self.assertEqual(res["total_language_count"], 25)
        self.assertEqual(res["present_dialects_count"], 8)

    def test_pseudo_codes_excluded(self):
        rich = GOZ + [{"lang_code": "donor", "word": "X"}, {"lang_code": "ai", "word": "Y"}]
        res = CognateAlignmentEngine().evaluate_cognate_distribution("göz", rich)
        self.assertEqual(res["present_dialects_count"], 8)

    def test_no_fabricated_baseline_score(self):
        """alignment_score sabit 85.0 tabanından GELMEMELİDİR."""
        res = CognateAlignmentEngine().evaluate_cognate_distribution("göz", GOZ)
        self.assertIsNotNone(res["alignment_score"])
        self.assertLessEqual(res["alignment_score"], 1.0)

    def test_empty_entries_have_no_evidence(self):
        res = CognateAlignmentEngine().evaluate_cognate_distribution("zzz", [])
        self.assertFalse(res["evidence_available"])
        self.assertIsNone(res["alignment_score"])


class TestCognateClustering(unittest.TestCase):
    def test_separates_distinct_roots(self):
        """*köŕ ailesi ile Sibirya *karak kökü AYRI kümelere düşmelidir."""
        mixed = GOZ + entries([("sah", "харах"), ("tyv", "карак")])
        res = CognateClusterEngine().cluster(mixed)
        self.assertTrue(res["evidence_available"])
        self.assertGreaterEqual(res["cluster_count"], 2)
        self.assertGreaterEqual(res["largest_cluster_size"], 8)

    def test_core_cognate_set_flag(self):
        res = CognateClusterEngine().cluster(GOZ)
        self.assertTrue(res["clusters"][0]["is_core_cognate_set"])

    def test_needs_two_forms(self):
        res = CognateClusterEngine().cluster(entries([("tr", "göz")]))
        self.assertFalse(res["evidence_available"])


class TestLoanwordClassifier(unittest.TestCase):
    def test_known_loanwords_are_not_native(self):
        """Regresyon: kitap/kalem/müdür/televizyon %100 'Öz Türkçe' çıkıyordu."""
        c = LoanwordClassifier()
        for w in ("kitap", "kalem", "müdür", "televizyon", "fistan", "coğrafya"):
            with self.subTest(word=w):
                res = c.classify(w)
                self.assertLess(res["probabilities"]["p_native_turkic"], 0.55, w)

    def test_native_words_stay_native(self):
        c = LoanwordClassifier()
        for w in ("göz", "deniz", "su", "ayak", "okul", "yastık"):
            with self.subTest(word=w):
                self.assertGreaterEqual(c.classify(w)["probabilities"]["p_native_turkic"], 0.55, w)

    def test_probabilities_sum_to_one(self):
        for w in ("kitap", "göz", "tren"):
            p = LoanwordClassifier().classify(w)["probabilities"]
            self.assertAlmostEqual(sum(p.values()), 1.0, places=2)

    def test_compound_words_exempt_from_vowel_harmony(self):
        """Bileşikler ünlü uyumunu doğal olarak bozar; alıntı sayılmamalıdır."""
        res = LoanwordClassifier().classify("bilgisayar")
        self.assertGreaterEqual(res["probabilities"]["p_native_turkic"], 0.55)

    def test_cross_dialect_spread_strengthens_native(self):
        c = LoanwordClassifier()
        wide = c.classify("kitap", spreading_ratio=0.8)["probabilities"]["p_native_turkic"]
        narrow = c.classify("kitap", spreading_ratio=0.05)["probabilities"]["p_native_turkic"]
        self.assertGreater(wide, narrow)

    def test_empty_word(self):
        self.assertFalse(LoanwordClassifier().classify("")["evidence_available"])


class TestLoanwordDetector(unittest.TestCase):
    def test_four_layer_pipeline(self):
        res = LoanwordDetector().detect("göz", GOZ)
        self.assertEqual(res["verdict"], "native")
        for layer in ("layer1_phonotactics", "layer2_cross_dialect",
                      "layer3_probabilities", "layer4_donor_neighbours"):
            self.assertIn(layer, res["layers"])

    def test_donor_lexicon_match_overrides_rules(self):
        res = LoanwordDetector().detect("kitap")
        self.assertEqual(res["verdict"], "loanword")
        self.assertIn("Arap", res["classification"])

    def test_method_is_declared_rule_based(self):
        """Sezgisel yöntem çıktıda AÇIKÇA bildirilmelidir."""
        res = LoanwordDetector().detect("göz", GOZ)
        self.assertEqual(res["method"], "rule_based")
        self.assertIn("ML", res["method_note"])

    def test_empty_word(self):
        self.assertFalse(LoanwordDetector().detect("")["evidence_available"])


class TestDonorLexicon(unittest.TestCase):
    def test_levenshtein(self):
        self.assertEqual(levenshtein("abc", "abc"), 0)
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertEqual(levenshtein("abc", ""), 3)
        self.assertEqual(levenshtein("kitten", "sitting"), 3)

    def test_ipa_distance_within_threshold(self):
        self.assertLessEqual(ipa_distance("kitap", "kitāb"), 2)
        self.assertGreater(ipa_distance("deniz", "kitap"), 2)

    def test_nearest_neighbours_finds_seed_donors(self):
        d = DonorLexicon()
        self.assertTrue(d.nearest_neighbours("kitap"))
        self.assertFalse(d.nearest_neighbours("zzzqxwv"))

    def test_empty_word(self):
        self.assertEqual(DonorLexicon().nearest_neighbours(""), [])


class TestDonorSearch(unittest.TestCase):
    def test_no_match_returns_none_not_placeholder(self):
        """Regresyon: eşleşme yokken donor_language'a '10 Komşu Dilde Canlı
        Taranıyor…' gibi SAHTE bir durum metni yazılıyordu."""
        res = DonorSearchEngine().search_donor_neighbors("zzzqx")
        self.assertFalse(res["found_match"])
        self.assertIsNone(res["donor_language"])

    def test_known_loanword_matches(self):
        res = DonorSearchEngine().search_donor_neighbors("kitap")
        self.assertTrue(res["found_match"])
        self.assertTrue(res["donor_language"])

    def test_empty(self):
        self.assertFalse(DonorSearchEngine().search_donor_neighbors("")["found_match"])


class TestNeologismDetector(unittest.TestCase):
    def test_compound_neologism(self):
        res = NeologismDetector().detect("bilgisayar")
        self.assertTrue(res["is_neologism"])
        self.assertEqual(res["components"], ["bilgi", "sayar"])

    def test_arabic_loans_not_flagged_as_neologisms(self):
        """Regresyon: -im/-ım eki 'hüküm', 'zulüm' gibi Arapça alıntıları
        'Cumhuriyet neolojizmi' sayıyordu."""
        d = NeologismDetector()
        for w in ("hüküm", "zulüm"):
            self.assertIsNone(d.detect(w), w)
        for w in ("resim", "takım"):
            res = d.detect(w)
            self.assertFalse(res["is_neologism"], w)

    def test_strong_suffixes(self):
        d = NeologismDetector()
        for w in ("toplumsal", "kurultay"):
            self.assertTrue(d.detect(w)["is_neologism"], w)

    def test_short_and_empty(self):
        self.assertIsNone(NeologismDetector().detect(""))
        self.assertIsNone(NeologismDetector().detect("ab"))


class TestHistoricalMorphology(unittest.TestCase):
    def test_builds_derivation_tree(self):
        t = HistoricalMorphologyAnalyzer().build_tree("güzellik")
        self.assertEqual(t["root"], "güzel")
        self.assertEqual(t["depth"], 1)

    def test_old_turkic_suffixes(self):
        """Plan §2.5'teki tarihsel ekler (+gU, -Ik, -gA, -bA) tanınmalıdır."""
        a = HistoricalMorphologyAnalyzer()
        self.assertEqual(a.build_tree("bitig")["root"], "biti")
        self.assertEqual(a.build_tree("susuz")["root"], "su")
        self.assertGreaterEqual(a.build_tree("toplumsal")["depth"], 2)

    def test_bare_root_has_zero_depth(self):
        self.assertEqual(HistoricalMorphologyAnalyzer().build_tree("at")["depth"], 0)

    def test_empty(self):
        self.assertFalse(HistoricalMorphologyAnalyzer().build_tree("")["evidence_available"])


class TestDerivationNetwork(unittest.TestCase):
    def test_generates_harmonic_candidates(self):
        """Ek seçimi ünlü uyumuna uymalıdır."""
        cands = {c["word"] for c in DerivationNetworkBuilder().candidate_derivations("göz")}
        self.assertIn("gözlük", cands)
        self.assertIn("gözsüz", cands)
        self.assertNotIn("gözluk", cands)

    def test_unverified_mode_needs_no_network(self):
        res = DerivationNetworkBuilder().build("göz", verify=False)
        self.assertTrue(res["evidence_available"])
        self.assertFalse(res["verified"])

    def test_short_root_rejected(self):
        self.assertFalse(DerivationNetworkBuilder().build("a", verify=False)["evidence_available"])


class TestSoundLawInduction(unittest.TestCase):
    def test_single_pair_has_no_confidence(self):
        """Tek çiftten güven skoru ÇIKARILAMAZ (eskiden sabit 0.95 veriliyordu)."""
        res = SoundLawInductionEngine().induce_sound_law("köz", "göz")
        self.assertIsNone(res["rule_confidence"])
        self.assertFalse(res["evidence_available"])

    def test_multi_pair_induction(self):
        pairs = [("köz", "göz"), ("kök", "gök"), ("kel", "gel"), ("kör", "gör"), ("küç", "güç")]
        res = SoundLawInductionEngine().induce_from_pairs(pairs)
        self.assertTrue(res["evidence_available"])
        rule = res["induced_rules"][0]
        self.assertEqual(rule["rule_id"], "INITIAL_K_G")
        self.assertEqual(rule["observed_in_pairs"], 5)
        self.assertGreater(rule["confidence"], 0.8)

    def test_needs_two_pairs(self):
        self.assertFalse(SoundLawInductionEngine().induce_from_pairs([("a", "b")])["evidence_available"])

    def test_identical_words_induce_nothing(self):
        res = SoundLawInductionEngine().induce_sound_law("göz", "göz")
        self.assertFalse(res["has_induced_rule"])


class TestSemanticEngine(unittest.TestCase):
    def test_deterministic_across_calls(self):
        e = DiachronicSemanticEngine()
        v1, _ = e.vectorizer.vectorise("deniz, büyük su")
        v2, _ = e.vectorizer.vectorise("deniz, büyük su")
        self.assertEqual(v1, v2)

    def test_missing_data_yields_no_evidence(self):
        res = DiachronicSemanticEngine().evaluate_diachronic_trajectory("", "")
        self.assertFalse(res["evidence_available"])
        self.assertIsNone(res["is_plausible"])

    def test_no_fabricated_acceleration_field(self):
        """Sahte 'ivme' alanı (mesafe × 1.10) kaldırılmalıydı."""
        res = DiachronicSemanticEngine().evaluate_diachronic_trajectory("göz", "göz")
        self.assertNotIn("semantic_acceleration", res)


class TestAttestationVerifier(unittest.TestCase):
    def test_no_fabricated_attestation(self):
        """Regresyon: kanıt yokken '13.-19. yy Osmanlı/Çağatay' cümlesi
        uyduruluyor, sonra A-HVP bunu 1850 yılı olarak okuyordu."""
        res = HistoricalAttestationVerifier().verify_attestation("zzzqx")
        self.assertFalse(res["verified"])
        self.assertIsNone(res["first_attestation_record"])
        self.assertIsNone(res["first_attestation_year"])

    def test_detects_known_sources(self):
        v = HistoricalAttestationVerifier()
        res = v.verify_attestation("deniz", [{"lang_name": "Divanü Lugati't-Türk (1074)"}])
        self.assertTrue(res["verified"])
        self.assertEqual(res["first_attestation_year"], 1074)

    def test_prefers_earliest(self):
        v = HistoricalAttestationVerifier()
        res = v.verify_attestation("su", [
            {"lang_name": "Kamus-ı Türkî"},
            {"lang_name": "Orhun Yazıtları"},
        ])
        self.assertEqual(res["first_attestation_year"], 735)

    def test_fetcher_attestation_is_used(self):
        v = HistoricalAttestationVerifier()
        res = v.verify_attestation("deniz", [], [{"first_attestation": {"year": 1070, "source": "DLT"}}])
        self.assertEqual(res["first_attestation_year"], 1070)


class TestMorphemeSegmenter(unittest.TestCase):
    def test_segments_suffixes(self):
        res = UnsupervisedMorphemeSegmenter().segment_morphemes("yağmurluk")
        self.assertTrue(res["is_segmented"])

    def test_short_word_not_over_segmented(self):
        res = UnsupervisedMorphemeSegmenter().segment_morphemes("at")
        self.assertGreaterEqual(len(res["stem"]), 2)


class TestHypothesisEngine(unittest.TestCase):
    def test_no_hypothesis_without_evidence(self):
        res = IterativeHypothesisEngine().prove_etymological_hypothesis(
            "qqqwww", {"root": {"proto_turkic": "", "meaning": ""}}, [], []
        )
        self.assertFalse(res["hypothesis_available"])
        self.assertIsNone(res["proven_hypothesis"])

    def test_comparative_hypothesis_from_cognates(self):
        res = IterativeHypothesisEngine().prove_etymological_hypothesis(
            "göz", {"root": {"proto_turkic": "", "meaning": "göz"}}, GOZ, []
        )
        self.assertTrue(res["hypothesis_available"])
        self.assertEqual(res["proven_hypothesis"]["origin_form"], "*köŕ")

    def test_donor_match_takes_priority(self):
        res = IterativeHypothesisEngine().prove_etymological_hypothesis(
            "kitap", {"root": {"proto_turkic": "", "meaning": "kitap"}}, [], []
        )
        self.assertTrue(res["hypothesis_available"])
        self.assertEqual(res["proven_hypothesis"]["evidence_kind"], "donor_lexicon")


if __name__ == "__main__":
    unittest.main()
