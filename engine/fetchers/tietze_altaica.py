from typing import Any

from engine.fetchers.base import BaseFetcher
from engine.utils.seed import load_seed_entries, seed_source_label

# Andreas Tietze, Monumenta Altaica ve Turuz Dijital Etimoloji Veri Külliyatı
#: Tohum (seed) veri. Kod içinde değil, data/seed/lexicon/tietze.json dosyasında tutulur.
SEED_PATH = "lexicon/tietze.json"
TIETZE_ALTAICA_LEXICON = load_seed_entries(SEED_PATH)

class TietzeAltaicaFetcher(BaseFetcher):
    #: Bu kaynak yerel tohum veriden beslenir, canlı bir servis DEĞİLDİR.
    is_seed_source = True

    @property
    def source_name(self) -> str:
        return seed_source_label("Tietze Etimoloji Külliyatı & Monumenta Altaica & Turuz Filoloji", SEED_PATH)

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        if word_clean in TIETZE_ALTAICA_LEXICON:
            entry = TIETZE_ALTAICA_LEXICON[word_clean]
            notes = f"{entry.get('tietze', '')} | {entry.get('altaica', '')} | {entry.get('turuz', '')}"
            result["root"]["reconstruction_notes"] = notes
            result["turkic_languages"].append({
                "lang_code": "otk",
                "lang_name": "Tietze & Altaica Etimolojik Corpus",
                "word": word_clean,
                "meaning": notes[:180] + "...",
                "script": "Latin"
            })

        return result
