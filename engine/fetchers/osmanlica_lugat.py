import re
import urllib.parse
import urllib.request
from typing import Any

from engine import config
from engine.fetchers.base import BaseFetcher
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get
from engine.utils.seed import load_seed_entries, seed_source_label
from engine.utils.text import strip_html

logger = get_logger(__name__)

# Dahili Osmanlıca ve Klasik Türkçe Lügat Dizini (Kubbealtı, Lehçe-i Osmanî, LexiQamus)
#: Tohum (seed) veri. Kod içinde değil, data/seed/lexicon/osmanlica.json dosyasında tutulur.
SEED_PATH = "lexicon/osmanlica.json"
OSMANLICA_LUGAT_INDEX = load_seed_entries(SEED_PATH)

class OsmanlicaLugatFetcher(BaseFetcher):
    #: Bu kaynak yerel tohum veriden beslenir, canlı bir servis DEĞİLDİR.
    is_seed_source = True

    @property
    def source_name(self) -> str:
        return seed_source_label("Osmanlıca ve Klasik Türkçe Lügat Portalları (Kubbealtı & Lehçe-i Osmanî)", SEED_PATH)

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        # 1. Dahili Sözlük Kontrolü
        if word_clean in OSMANLICA_LUGAT_INDEX:
            entry = OSMANLICA_LUGAT_INDEX[word_clean]
            result["turkic_languages"].append({
                "lang_code": "ota",
                "lang_name": f"Osmanlıca Lügat ({entry['source']})",
                "word": entry["word_osmanli"],
                "meaning": entry["meaning"],
                "script": "Arabic"
            })
            result["root"]["reconstruction_notes"] = f"Osmanlıca Lügat Kaydı: {entry['meaning']}"

        # 2. Canlı Lugatim Web İsteği
        url = f"https://www.lugatim.com/s/{urllib.parse.quote(word_clean)}"
        try:
            _body = http_get(url, timeout=config.HTTP_TIMEOUT_MEDIUM)
            if _body is not None:
                html = _body
                m = re.search(r'<div class=\"[^\"]*meaning[^\"]*\"[^>]*>(.*?)</div>', html, re.DOTALL)
                if m:
                    clean_m = strip_html(m.group(1)).strip()
                    if clean_m:
                        result["turkic_languages"].append({
                            "lang_code": "ota",
                            "lang_name": "Kubbealtı Lugatı (Lugatim.com Live)",
                            "word": word_clean,
                            "meaning": clean_m[:150],
                            "script": "Latin"
                        })
        except Exception:
            logger.warning("%s: kaynak işlenemedi", self.source_name if hasattr(self, "source_name") else __name__, exc_info=True)
        return result
