import re
from typing import Any

from engine.fetchers.base import TURKIC_LANGUAGES_MAP, BaseFetcher
from engine.utils.seed import load_seed_entries, seed_source_label

# Dahili Yıldız/Starling Proto-Türkçe Etimoloji Sözlük Dizini (Core Turkic Lexicon Index)
#: Tohum (seed) veri. Kod içinde değil, data/seed/lexicon/starling.json dosyasında tutulur.
SEED_PATH = "lexicon/starling.json"
STARLING_OFFLINE_LEXICON = load_seed_entries(SEED_PATH)

class StarlingFetcher(BaseFetcher):
    #: Bu kaynak yerel tohum veriden beslenir, canlı bir servis DEĞİLDİR.
    is_seed_source = True

    @property
    def source_name(self) -> str:
        return seed_source_label("Starling Etymological Database", SEED_PATH)

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {
                "proto_turkic": "",
                "meaning": "",
                "reconstruction_notes": ""
            },
            "turkic_languages": []
        }

        if word_clean in STARLING_OFFLINE_LEXICON:
            entry = STARLING_OFFLINE_LEXICON[word_clean]
            result["root"]["proto_turkic"] = entry["proto_turkic"]
            result["root"]["meaning"] = entry["meaning"]
            result["root"]["reconstruction_notes"] = f"Starling / Tower of Babel Proto-Turkic reconstruction {entry['proto_turkic']}"

            for lang_code, cognate in entry["cognates"].items():
                if lang_code in TURKIC_LANGUAGES_MAP:
                    display_word = cognate["word"]
                    result["turkic_languages"].append({
                        "lang_code": lang_code,
                        "lang_name": TURKIC_LANGUAGES_MAP[lang_code],
                        "word": display_word,
                        "meaning": cognate["meaning"],
                        "script": "Cyrillic" if re.search(r'[\u0400-\u04FF]', display_word) else ("Arabic" if re.search(r'[\u0600-\u06FF]', display_word) else "Latin")
                    })

        return result
