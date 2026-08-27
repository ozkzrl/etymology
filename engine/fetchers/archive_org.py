import json
import urllib.parse
import urllib.request
from typing import Any

from engine import config
from engine.fetchers.base import BaseFetcher
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get

logger = get_logger(__name__)


class ArchiveOrgFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "Internet Archive (Archive.org Dijital Kitaplar Külliyatı)"

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        query = f"{word_clean} turkic etymology"
        url = f"https://archive.org/advancedsearch.php?q={urllib.parse.quote(query)}&fl[]=identifier,title,creator,year&rows=2&page=1&output=json"
        try:
            _body = http_get(url, timeout=config.HTTP_TIMEOUT_MEDIUM)
            if _body is not None:
                data = json.loads(_body)
                docs = data.get("response", {}).get("docs", [])
                for doc in docs:
                    title = doc.get("title", "")
                    creator = doc.get("creator", "Bilinmeyen Yazar")
                    year = doc.get("year", "Tarihsiz")
                    if title:
                        result["turkic_languages"].append({
                            "lang_code": "otk",
                            "lang_name": f"Archive.org Kitap Külliyatı ({year})",
                            "word": word_clean,
                            "meaning": f"Kitap: {title} (Yazar: {creator})",
                            "script": "Latin"
                        })
                        result["root"]["reconstruction_notes"] = f"Archive.org Dijital Kitap: {title} ({year})"
        except Exception:
            logger.warning("%s: kaynak işlenemedi", self.source_name if hasattr(self, "source_name") else __name__, exc_info=True)
        return result
