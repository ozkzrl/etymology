"""
engine/utils/ Katmanı Birim Testleri

Bu katman daha önce **tamamen test edilmemişti** (9 modül, %0 kapsam).
"""
from __future__ import annotations

import unittest

from engine.utils.cognates import get_related_cognates
from engine.utils.geo_tagger import tag_geographical_region
from engine.utils.morphology import analyze_morphology
from engine.utils.orthography import (
    strip_non_turkic,
    to_comparison_form,
    to_expected_reflex,
)
from engine.utils.phonetic_rules import analyze_phonetic_shifts, verify_phonetic_chain
from engine.utils.phonotactics import (
    PERSIAN_SUFFIXES,
    WESTERN_SUFFIXES,
    has_vowel_harmony,
    initial_cluster_violation,
    initial_consonant_violation,
    match_arabic_pattern,
    match_greek_latin_pattern,
    match_suffix,
)
from engine.utils.reference_resolver import extract_cross_references
from engine.utils.sound_shifts import generate_turkic_cognate_candidates
from engine.utils.text import strip_html, truncate
from engine.utils.transliteration import transliterate_to_latin
from engine.utils.variant_expander import generate_dynamic_phonetic_variants


class TestOrthography(unittest.TestCase):
    """Kiril karakter sınıfı regresyonları."""

    def test_cyrillic_turkic_letters_are_preserved(self):
        """Türki Kiril harfleri BUDANMAMALIDIR.

        Regresyon: eski `[^a-zçğıöşüа-я...]` deseni `ө ҫ ҙ һ ң` gibi harfleri
        kapsamıyordu; `көз` -> `кз`, `теңіз` -> `тез`, `куҫ` -> `ку` oluyordu.
        """
        cases = {"көз": "көз", "теңіз": "теңіз", "куҫ": "куҫ", "һыу": "һыу", "күҙ": "күҙ"}
        for src, expected in cases.items():
            self.assertEqual(strip_non_turkic(src), expected, f"{src} budandı")

    def test_comparison_form_maps_cyrillic_to_latin(self):
        self.assertEqual(to_comparison_form("көз"), "köz")
        self.assertEqual(to_comparison_form("теңіз"), "teŋiz")
        self.assertEqual(to_comparison_form("куҫ"), "kus")
        self.assertEqual(to_comparison_form("*köŕ"), "köŕ")

    def test_comparison_form_handles_empty_and_none(self):
        self.assertEqual(to_comparison_form(""), "")
        self.assertEqual(to_comparison_form(None), "")

    def test_expected_reflex_maps_proto_phonemes(self):
        """Ata sesler Ortak Türkçe reflekslerine çevrilmelidir."""
        self.assertEqual(to_expected_reflex("*köŕ"), "köz")
        self.assertEqual(to_expected_reflex("*jol"), "yol")
        self.assertEqual(to_expected_reflex("*teŋiŕ"), "teniz")

    def test_arabic_and_runic_scripts_preserved(self):
        self.assertEqual(strip_non_turkic("كتاب"), "كتاب")
        self.assertTrue(strip_non_turkic("𐰆𐰉"))


class TestPhonotactics(unittest.TestCase):
    def test_vowel_harmony(self):
        for w in ("deniz", "göz", "araba", "gözlük", "su"):
            self.assertTrue(has_vowel_harmony(w), w)
        for w in ("kitap", "televizyon", "kalem"):
            self.assertFalse(has_vowel_harmony(w), w)

    def test_single_vowel_words_are_harmonic(self):
        self.assertTrue(has_vowel_harmony("el"))
        self.assertTrue(has_vowel_harmony("at"))
        self.assertTrue(has_vowel_harmony(""))

    def test_initial_consonant_violation(self):
        self.assertTrue(initial_consonant_violation("fistan")[0])
        self.assertTrue(initial_consonant_violation("hane")[0])
        self.assertFalse(initial_consonant_violation("göz")[0])
        self.assertFalse(initial_consonant_violation("deniz")[0])
        self.assertFalse(initial_consonant_violation("")[0])

    def test_initial_cluster_violation(self):
        self.assertTrue(initial_cluster_violation("tren")[0])
        self.assertTrue(initial_cluster_violation("stres")[0])
        self.assertFalse(initial_cluster_violation("göz")[0])

    def test_arabic_patterns_actually_fire(self):
        """Arapça vezin desenleri TÜRKÇE imlada tetiklenmelidir.

        Regresyon: eski desenler makronlu (ī, ā) Latin harfleri bekliyordu;
        girdi Türkçe imla olduğu için hiçbir zaman eşleşmiyorlardı.
        """
        self.assertIsNotNone(match_arabic_pattern("müdür"))
        self.assertIsNotNone(match_arabic_pattern("mektup"))
        self.assertIsNotNone(match_arabic_pattern("istiklal"))
        self.assertIsNone(match_arabic_pattern("deniz"))
        self.assertIsNone(match_arabic_pattern("göz"))

    def test_persian_and_western_suffixes(self):
        self.assertIsNotNone(match_suffix("gülistan", PERSIAN_SUFFIXES))
        self.assertIsNotNone(match_suffix("hastane", PERSIAN_SUFFIXES))
        self.assertIsNotNone(match_suffix("sosyalizm", WESTERN_SUFFIXES))
        self.assertIsNone(match_suffix("göz", PERSIAN_SUFFIXES))

    def test_greek_latin_patterns(self):
        self.assertIsNotNone(match_greek_latin_pattern("kozmos"))
        self.assertIsNone(match_greek_latin_pattern("deniz"))


class TestPhoneticRules(unittest.TestCase):
    def test_regular_correspondences_are_valid(self):
        for origin, modern in [("*köŕ", "göz"), ("*teŋiŕ", "deniz"), ("*jol", "yol")]:
            res = verify_phonetic_chain(origin, modern)
            self.assertTrue(res["is_valid"], f"{origin} -> {modern}")
            self.assertGreater(res["score"], 0.55)

    def test_unrelated_forms_are_rejected(self):
        """Karakter KÜMESİ değil, SIRALI dizi karşılaştırılmalıdır.

        Regresyon: 'kös' ile 'sök' aynı harfleri taşıdığı için %100
        benzer sayılıyordu.
        """
        res = verify_phonetic_chain("kös", "sök")
        self.assertFalse(res["is_valid"])

    def test_empty_target_yields_no_evidence(self):
        res = verify_phonetic_chain("*köŕ", "")
        self.assertFalse(res["evidence_available"])
        self.assertIsNone(res["score"])

    def test_identical_forms_score_one(self):
        res = verify_phonetic_chain("göz", "göz")
        self.assertEqual(res["score"], 1.0)
        self.assertTrue(res["is_valid"])

    def test_turkish_c_words_not_flagged_as_western(self):
        """Söz başı 'c-' tek başına Batı alıntısı göstergesi DEĞİLDİR.

        Regresyon: desendeki tek harflik `c` alternatifi 'can', 'cam', 'cep'
        gibi tüm c- kelimelerini "Fransızca fonotaktik uyarlaması" sayıyordu.
        """
        for w in ("can", "cam", "cep", "cadde"):
            self.assertNotIn("Fransızca", analyze_phonetic_shifts(w, w), w)

    def test_western_clusters_still_detected(self):
        self.assertIn("Fransızca", analyze_phonetic_shifts("tren", "tren"))


class TestSoundShifts(unittest.TestCase):
    def test_variants_are_deterministic(self):
        """Varyant listesi çalıştırmadan çalıştırmaya DEĞİŞMEMELİDİR.

        Regresyon: `set` yinelemesi PYTHONHASHSEED'e bağlıydı; MAX_VARIANTS
        ile kırpıldığında her seferinde farklı varyantlar aranıyordu.
        """
        first = generate_turkic_cognate_candidates("deniz")
        for _ in range(5):
            self.assertEqual(generate_turkic_cognate_candidates("deniz"), first)
        self.assertEqual(first, sorted(first))

    def test_no_spurious_substring_matches(self):
        """'su' KÖKÜ, 'usul'/'masum'/'kusur' kelimelerine uygulanmamalıdır.

        Regresyon: substring eşleşmesi bu kelimelere 9 sahte varyant ekliyor,
        her biri 18 fetcher'a boşa istek attırıyordu.
        """
        seed_forms = {"суу", "һыу", "шыв", "суг"}
        for w in ("usul", "masum", "kusur", "susmak", "basur"):
            got = set(generate_turkic_cognate_candidates(w))
            self.assertFalse(got & seed_forms, f"{w} sahte 'su' varyantı aldı")

    def test_vowel_rule_changes_only_first_occurrence(self):
        """Ünlü kuralı TÜM eşleşmeleri değiştirmemelidir ('deneme' -> 'dinimi')."""
        variants = generate_turkic_cognate_candidates("deneme")
        self.assertIn("dineme", variants)
        self.assertNotIn("dinimi", variants)

    def test_empty_input(self):
        self.assertEqual(generate_turkic_cognate_candidates(""), [])
        self.assertEqual(generate_dynamic_phonetic_variants(""), [])

    def test_query_word_is_first_variant(self):
        self.assertEqual(generate_dynamic_phonetic_variants("göz")[0], "göz")


class TestMorphology(unittest.TestCase):
    def test_suffix_stripping(self):
        stem, suffixes = analyze_morphology("güzellik")
        self.assertEqual(stem, "güzel")
        self.assertTrue(suffixes)

    def test_bare_root_has_no_suffix(self):
        stem, suffixes = analyze_morphology("göz")
        self.assertEqual(stem, "göz")
        self.assertEqual(suffixes, [])

    def test_empty_input(self):
        stem, suffixes = analyze_morphology("")
        self.assertEqual(stem, "")
        self.assertEqual(suffixes, [])


class TestTextHelpers(unittest.TestCase):
    def test_strip_html_removes_tags_and_entities(self):
        self.assertEqual(strip_html("<p>merhaba &amp; <b>dünya</b></p>"), "merhaba & dünya")

    def test_strip_html_removes_script_and_style(self):
        out = strip_html("<div>metin</div><script>alert(1)</script><style>a{}</style>")
        self.assertNotIn("alert", out)
        self.assertIn("metin", out)

    def test_strip_html_handles_none(self):
        self.assertEqual(strip_html(None), "")

    def test_truncate(self):
        self.assertEqual(truncate("abcdef", 10), "abcdef")
        self.assertTrue(truncate("abcdefghij", 5).endswith("…"))
        self.assertLessEqual(len(truncate("abcdefghij", 5)), 5)


class TestTransliteration(unittest.TestCase):
    def test_cyrillic_to_latin(self):
        out = transliterate_to_latin("теңіз")
        self.assertTrue(out)
        self.assertNotEqual(out, "теңіз")

    def test_latin_input_unchanged_shape(self):
        self.assertIsInstance(transliterate_to_latin("deniz"), str)

    def test_empty(self):
        self.assertEqual(transliterate_to_latin(""), "")


class TestGeoTagger(unittest.TestCase):
    def test_known_city_gets_coordinates(self):
        res = tag_geographical_region("TDK Derleme (Trabzon)")
        self.assertEqual(res["location"], "Trabzon")
        self.assertIsNotNone(res["geo_coordinates"])

    def test_unknown_location_has_no_coordinates(self):
        res = tag_geographical_region("bilinmeyen yer")
        self.assertIsNone(res["geo_coordinates"])


class TestReferenceResolver(unittest.TestCase):
    def test_extracts_arrow_references(self):
        refs = extract_cross_references("bkz. -> derya")
        self.assertIn("derya", refs)

    def test_no_reference(self):
        self.assertEqual(extract_cross_references("düz tanım"), [])

    def test_empty(self):
        self.assertEqual(extract_cross_references(""), [])


class TestCognates(unittest.TestCase):
    def test_collects_related_forms(self, ):
        entries = [
            {"lang_code": "kk", "word": "көз", "lang_name": "Kazakça"},
            {"lang_code": "cv", "word": "куҫ", "lang_name": "Çuvaşça"},
        ]
        out = get_related_cognates("göz", entries)
        self.assertIsInstance(out, list)

    def test_empty_entries(self):
        self.assertIsInstance(get_related_cognates("göz", []), list)


if __name__ == "__main__":
    unittest.main()
