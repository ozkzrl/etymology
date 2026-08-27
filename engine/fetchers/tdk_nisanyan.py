import json
import re
import urllib.parse
import urllib.request
from typing import Any

from engine import config
from engine.fetchers.base import TURKIC_LANGUAGES_MAP, BaseFetcher
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get

logger = get_logger(__name__)


class TdkFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "TDK (Türk Dil Kurumu)"

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        url = f"https://sozluk.gov.tr/gts?ara={urllib.parse.quote(word_clean)}"
        try:
            _body = http_get(url, timeout=config.HTTP_TIMEOUT_MEDIUM)
            if _body is not None:
                data = json.loads(_body)
                if isinstance(data, list) and len(data) > 0 and "anlamlarListe" in data[0]:
                    meanings = [item["anlam"] for item in data[0]["anlamlarListe"] if "anlam" in item]
                    meaning_str = "; ".join(meanings[:2])

                    lisan = data[0].get("lisan", "")

                    result["turkic_languages"].append({
                        "lang_code": "tr",
                        "lang_name": TURKIC_LANGUAGES_MAP["tr"],
                        "word": word_clean,
                        "meaning": meaning_str,
                        "script": "Latin"
                    })
                    result["root"]["meaning"] = meaning_str
                    if lisan:
                        result["root"]["reconstruction_notes"] = f"TDK Köken Bilgisi: {lisan}"
        except Exception:
            logger.warning("%s: kaynak işlenemedi", self.source_name if hasattr(self, "source_name") else __name__, exc_info=True)
        return result


class NisanyanFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "Nişanyan Etimoloji Sözlüğü"

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        url = f"https://www.nisanyansozluk.com/kelime/{urllib.parse.quote(word_clean)}"
        try:
            _body = http_get(url, timeout=config.HTTP_TIMEOUT_LONG)
            if _body is not None:
                html = _body
                tokens = re.findall(r'text:\"([^\"]+)\"', html)
                if not tokens:
                    return result

                text_full = "".join(tokens)

                # Eski Türkçe veya Ana Türkçe kök tespiti
                etü_match = re.search(r'Eski\s+Türkçe\s+([a-zçğıöşüA-ZÇĞİÖŞÜ\*]+)\s+“([^”]+)”', text_full)
                if etü_match:
                    etü_word = etü_match.group(1).strip()
                    etü_meaning = etü_match.group(2).strip()
                    result["turkic_languages"].append({
                        "lang_code": "otk",
                        "lang_name": TURKIC_LANGUAGES_MAP["otk"],
                        "word": etü_word,
                        "meaning": etü_meaning,
                        "script": "Latin"
                    })
                    result["root"]["proto_turkic"] = f"*{etü_word}"
                    result["root"]["meaning"] = etü_meaning

                # Alıntı köken tespiti (Ermenice, Grekçe, Farsça, Arapça, Fransızca, İtalyanca vb.)
                donor_match = re.search(r'(Ermenice|Grekçe|Farsça|Arapça|Fransızca|İtalyanca|Rumca|Latince|Eski Farsça|Süryanice)\s+([a-zçğıöşüA-ZÇĞİÖŞÜ\*\'\`\-]+)\s+“([^”]+)”', text_full)
                if donor_match:
                    d_lang = donor_match.group(1).strip()
                    d_word = donor_match.group(2).strip()
                    d_meaning = donor_match.group(3).strip()
                    result["root"]["proto_turkic"] = f"[{d_lang}] {d_word}"
                    if not result["root"]["meaning"]:
                        result["root"]["meaning"] = d_meaning
                    result["root"]["reconstruction_notes"] = f"Nişanyan Alıntı Kaynağı: {d_lang} '{d_word}' ({d_meaning})"

                # Ana Türkçe / Proto-Turkic kök tespiti
                root_match = re.search(r'\*([a-zçğıöşüA-ZÇĞİÖŞÜ\-]+)\s+“([^”]+)”', text_full)
                if root_match:
                    proto_w = root_match.group(1).strip()
                    proto_m = root_match.group(2).strip()
                    result["root"]["proto_turkic"] = f"*{proto_w}"
                    if not result["root"]["meaning"]:
                        result["root"]["meaning"] = proto_m

                if not result["root"]["reconstruction_notes"]:
                    result["root"]["reconstruction_notes"] = f"Nişanyan Etimoloji: {text_full[:300]}..."

        except Exception:
            logger.warning("%s: kaynak işlenemedi", self.source_name if hasattr(self, "source_name") else __name__, exc_info=True)
        return result
