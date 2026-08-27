import json
import urllib.parse
import urllib.request
from typing import Any

from engine import config
from engine.fetchers.base import BaseFetcher
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get

logger = get_logger(__name__)


class TdkTaramaFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "TDK Tarama Sözlüğü (Tarihi Türkçe Metinler 13.-19. yy)"

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        url = f"https://sozluk.gov.tr/tarama?ara={urllib.parse.quote(word_clean)}"
        try:
            _body = http_get(url, timeout=config.HTTP_TIMEOUT_MEDIUM)
            if _body is not None:
                data = json.loads(_body)
                if isinstance(data, list) and len(data) > 0:
                    item = data[0]
                    tarama_list = item.get("tarama", [])
                    if tarama_list:
                        hist_word = tarama_list[0].get("kelime", word_clean)
                        meaning = tarama_list[0].get("anlam", "")
                        result["turkic_languages"].append({
                            "lang_code": "otk",
                            "lang_name": "Tarihi Türkçe / Osmanlıca (13.-19. yy)",
                            "word": hist_word,
                            "meaning": meaning,
                            "script": "Latin"
                        })
                        result["root"]["reconstruction_notes"] = f"TDK Tarama Sözlüğü (Tarihi Türkçe): {hist_word} - {meaning}"
        except Exception:
            logger.warning("%s: kaynak işlenemedi", self.source_name if hasattr(self, "source_name") else __name__, exc_info=True)
        return result


class TdkDerlemeFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "TDK Derleme Sözlüğü (Türk Ağızları ve Diyalektleri)"

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        url = f"https://sozluk.gov.tr/derleme?ara={urllib.parse.quote(word_clean)}"
        try:
            _body = http_get(url, timeout=config.HTTP_TIMEOUT_MEDIUM)
            if _body is not None:
                data = json.loads(_body)
                if isinstance(data, list) and len(data) > 0:
                    for item in data[:3]:
                        m_word = item.get("madde", word_clean)
                        meaning = item.get("anlam", "")
                        city = item.get("sehir", "")
                        if meaning:
                            result["turkic_languages"].append({
                                "lang_code": "tr",
                                "lang_name": f"Türk Ağızları ({city})" if city else "Türk Ağızları",
                                "word": m_word,
                                "meaning": meaning,
                                "script": "Latin"
                            })
        except Exception:
            logger.warning("%s: kaynak işlenemedi", self.source_name if hasattr(self, "source_name") else __name__, exc_info=True)
        return result
