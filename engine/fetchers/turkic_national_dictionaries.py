import re
from typing import Any

from engine.fetchers.base import BaseFetcher
from engine.utils.seed import load_seed_entries, seed_source_label

# Türki Cumhuriyetler Yerel İzahlı Lügat İndeksi (Obastan, Savodxon, Tilqazyna, ElSözlük)
#: Tohum (seed) veri. Kod içinde değil, data/seed/lexicon/turkic_national.json dosyasında tutulur.
SEED_PATH = "lexicon/turkic_national.json"
TURKIC_NATIONAL_LEXICON = load_seed_entries(SEED_PATH)

class TurkicNationalDictionariesFetcher(BaseFetcher):
    #: Bu kaynak yerel tohum veriden beslenir, canlı bir servis DEĞİLDİR.
    is_seed_source = True

    @property
    def source_name(self) -> str:
        return seed_source_label("Türki Cumhuriyetler Yerel İzahlı Lügat Portalları (Obastan, Savodxon, Tilqazyna, ElSözlük)", SEED_PATH)

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        if word_clean in TURKIC_NATIONAL_LEXICON:
            for entry in TURKIC_NATIONAL_LEXICON[word_clean]:
                result["turkic_languages"].append({
                    "lang_code": entry["code"],
                    "lang_name": entry["name"],
                    "word": entry["word"],
                    "meaning": entry["meaning"],
                    "script": "Cyrillic" if re.search(r'[\u0400-\u04FF]', entry["word"]) else "Latin"
                })

        return result
