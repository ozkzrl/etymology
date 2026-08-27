from typing import Any

from engine.fetchers.base import BaseFetcher
from engine.utils.seed import load_seed_entries, seed_source_label

# Divanü Lugati't-Türk (1074), Kamus-ı Türkî (1901), Codex Cumanicus (1303), Mukaddimetü'l-Edeb (12. yy), Sanglax & Güncel Sözlükler
#: Tohum (seed) veri. Kod içinde değil, data/seed/lexicon/dlt_kamus.json dosyasında tutulur.
SEED_PATH = "lexicon/dlt_kamus.json"
HISTORICAL_MODERN_LEXICON = load_seed_entries(SEED_PATH)

class HistoricalModernLexiconFetcher(BaseFetcher):
    #: Bu kaynak yerel tohum veriden beslenir, canlı bir servis DEĞİLDİR.
    is_seed_source = True

    @property
    def source_name(self) -> str:
        return seed_source_label("Tarihi Türk Lehçeleri Sözlükleri (DLT 1074, Kamus-ı Türkî 1901, Codex Cumanicus 1303, Sanglax)", SEED_PATH)

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        if word_clean in HISTORICAL_MODERN_LEXICON:
            entry = HISTORICAL_MODERN_LEXICON[word_clean]

            if "dlt" in entry:
                result["turkic_languages"].append({
                    "lang_code": "otk",
                    "lang_name": "Divanü Lugati't-Türk (Kaşgarlı Mahmud, 1074)",
                    "word": word_clean,
                    "meaning": entry["dlt"],
                    "script": "Latin / Arabic"
                })

            if "kamus" in entry:
                result["turkic_languages"].append({
                    "lang_code": "ota",
                    "lang_name": "Kamus-ı Türkî (Şemseddin Sami, 1901)",
                    "word": word_clean,
                    "meaning": entry["kamus"],
                    "script": "Latin / Arabic"
                })

            if "codex" in entry:
                result["turkic_languages"].append({
                    "lang_code": "chg",  # Codex Cumanicus: tarihî Kıpçak/Kuman metni (modern krc DEĞİL)
                    "lang_name": "Codex Cumanicus (Kıpçakça Metinler, 1303)",
                    "word": word_clean,
                    "meaning": entry["codex"],
                    "script": "Latin"
                })

            if "sanglax" in entry:
                result["turkic_languages"].append({
                    "lang_code": "chg",
                    "lang_name": "Sanglax (Klasik Çağatayca Nevai Sözlüğü)",
                    "word": word_clean,
                    "meaning": entry["sanglax"],
                    "script": "Latin / Arabic"
                })

        return result
