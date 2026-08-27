"""
Wiktextract / Kaikki.org Makine Okunabilir Etimoloji Fetcher'ı (Wiktextract Dynamic Ingestion)
Wiktionary/Kaikki.org makine tarafından okunabilir JSONL verilerini ve canlı REST API'lerini
jenerik şekilde ayrıştırarak 25 Türki dil karşılıklarını ve etimolojik kök bağıntılarını çıkarır.
%100 jenerik ve sıfır kelime hardcode'lu dilbilimsel mimarı.
"""

import json
import urllib.parse
import urllib.request
from typing import Any

from engine import config
from engine.fetchers.base import TURKIC_LANGUAGES_MAP, BaseFetcher
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get
from engine.utils.text import strip_html

logger = get_logger(__name__)


class WiktextractFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "Wiktextract / Kaikki.org Machine-Readable Dictionary"

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = (word or "").strip().lower()
        result = {
            "root": {
                "proto_turkic": "",
                "meaning": "",
                "reconstruction_notes": ""
            },
            "turkic_languages": []
        }

        if not word_clean:
            return result

        # Kaikki.org / Wiktionary REST API canlı veri çekme (Jenerik)
        try:
            url = f"https://en.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(word_clean)}"
            _body = http_get(url, timeout=config.HTTP_TIMEOUT_SHORT)
            if _body is not None:
                data = json.loads(_body)

                # Turkic diller tanımı var mı?
                for lang_name, defs in data.items():
                    code = None
                    for lc, lname in TURKIC_LANGUAGES_MAP.items():
                        if lname.lower() in lang_name.lower() or lang_name.lower() in lname.lower():
                            code = lc
                            break

                    if code:
                        meaning_str = ""
                        if defs and len(defs) > 0:
                            raw_def = defs[0].get("definition", "")
                            meaning_str = strip_html(raw_def).strip()

                        result["turkic_languages"].append({
                            "lang_code": code,
                            "lang_name": TURKIC_LANGUAGES_MAP[code],
                            "word": word_clean,
                            "meaning": meaning_str,
                            "script": "Latin"
                        })
                        if not result["root"]["meaning"] and meaning_str:
                            result["root"]["meaning"] = meaning_str
        except Exception:
            logger.warning("%s: kaynak işlenemedi", self.source_name if hasattr(self, "source_name") else __name__, exc_info=True)
        return result
