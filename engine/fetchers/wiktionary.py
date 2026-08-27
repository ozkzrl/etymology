import json
import re
import urllib.parse
import urllib.request
from typing import Any

from engine import config
from engine.fetchers.base import (
    TURKIC_LANGUAGES_MAP,
    BaseFetcher,
    detect_script,
    lang_code_from_wiktionary_header,
)
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get

logger = get_logger(__name__)


class WiktionaryFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "Wiktionary"

    def _http_get(self, url: str) -> str | None:
        return http_get(url, timeout=config.HTTP_TIMEOUT_LONG)

    def _get_page_wikitext(self, page_title: str) -> str | None:
        url = f"https://en.wiktionary.org/w/api.php?action=parse&page={urllib.parse.quote(page_title)}&format=json&prop=wikitext"
        raw = self._http_get(url)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            logger.warning("Wiktionary wikitext JSON ayrıştırılamadı: %s", page_title, exc_info=True)
            return None
        if "error" in data:
            logger.debug("Wiktionary sayfası yok: %s", page_title)
            return None
        return data.get("parse", {}).get("wikitext", {}).get("*", "")

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

        # 1. Ana kelime sayfasını çek
        wt = self._get_page_wikitext(word_clean)
        proto_page_title = None

        if wt:
            # Proto-Turkic kök bağlantısını ara (örn. {{inh|tr|trk-pro|*sub|t=water}})
            proto_match = re.search(r'\{\{(?:inh|der|cog)\|[a-z\-]+\|trk-pro\|\*?([^|\}]+)(?:\|t=([^|\}]+))?', wt)
            if proto_match:
                proto_root = proto_match.group(1).strip()
                proto_meaning = proto_match.group(2).strip() if proto_match.group(2) else ""
                result["root"]["proto_turkic"] = f"*{proto_root}"
                result["root"]["meaning"] = proto_meaning
                proto_page_title = f"Reconstruction:Proto-Turkic/{proto_root}"

        # 2. Eğer Proto-Turkic rekonstruksiyon sayfası bulunursa, akraba kelimeleri oradan çek
        if proto_page_title:
            recon_wt = self._get_page_wikitext(proto_page_title)
            if recon_wt:
                self._parse_reconstruction_page(recon_wt, result)

        # 3. Ana sayfadan da tanımları ve Türki dilleri topla
        if wt:
            self._parse_word_page(wt, word_clean, result)

        return result

    def _parse_reconstruction_page(self, wt: str, result: dict[str, Any]) -> None:
        # Anlam çekme
        meaning_match = re.search(r'==Proto-Turkic==.*?(?:#\s*\[\[(.*?)\]\]|#\s*(.*?)\n)', wt, re.DOTALL)
        if meaning_match and not result["root"]["meaning"]:
            meaning = (meaning_match.group(1) or meaning_match.group(2) or "").strip()
            result["root"]["meaning"] = meaning

        # Türki diller türevlerini parsing
        # Template format: {{desc|code|word|...}} veya {{desctree|code|word|...}}
        desc_pattern = r'\{\{desc(?:tree)?\|([a-z0-9\-]+)\|([^|\}]+)(?:\|([^|\}]+))?(?:\|ts=([^|\}]+))?'

        seen_langs = {item["lang_code"]: item for item in result["turkic_languages"]}

        for match in re.finditer(desc_pattern, wt):
            lang_code = match.group(1).strip()
            entry_word = match.group(2).strip()
            extra_word = match.group(3) or ""
            ts_trans = match.group(4) or ""

            # Türki diller haritasında var mı?
            if lang_code in TURKIC_LANGUAGES_MAP:
                display_word = entry_word
                if ts_trans and not ts_trans.startswith("t="):
                    display_word = f"{entry_word} ({ts_trans})"
                elif extra_word and not extra_word.startswith("t=") and not extra_word.startswith("bor="):
                    display_word = f"{entry_word} ({extra_word})"

                if lang_code not in seen_langs:
                    item = {
                        "lang_code": lang_code,
                        "lang_name": TURKIC_LANGUAGES_MAP[lang_code],
                        "word": display_word,
                        "meaning": result["root"]["meaning"],
                        "script": detect_script(display_word),
                    }
                    result["turkic_languages"].append(item)
                    seen_langs[lang_code] = item

    def _parse_word_page(self, wt: str, word_clean: str, result: dict[str, Any]) -> None:
        seen_langs = {item["lang_code"]: item for item in result["turkic_languages"]}

        # Yalnızca 2. seviye dil başlıkları: ==Turkish==, ==Azerbaijani==
        # Not: eski desen `===Noun===` gibi ALT başlıkları da yakalıyor ve
        # bölüm içeriğini ikiye bölerek anlamların kaybolmasına yol açıyordu.
        lang_sections = re.split(r'^==\s*([^=\n]+?)\s*==\s*$', wt, flags=re.M)
        for i in range(1, len(lang_sections) - 1, 2):
            lang_header = lang_sections[i].strip()
            section_content = lang_sections[i+1]

            # Wiktionary başlıkları İNGİLİZCEDİR ("==Turkish=="); harita ise
            # Türkçe adlar tutar. Doğrudan karşılaştırma hiçbir zaman
            # eşleşmiyordu ve bu ayrıştırıcı fiilen ölüydü.
            code = lang_code_from_wiktionary_header(lang_header)

            if code and code not in seen_langs:
                # Anlam çıkar
                m = re.search(r'#\s*\[\[(.*?)\]\]|#\s*(.*?)\n', section_content)
                meaning = ""
                if m:
                    meaning = (m.group(1) or m.group(2) or "").strip()

                item = {
                    "lang_code": code,
                    "lang_name": TURKIC_LANGUAGES_MAP[code],
                    "word": word_clean,
                    "meaning": meaning or result["root"]["meaning"],
                    "script": detect_script(word_clean),
                }
                result["turkic_languages"].append(item)
                seen_langs[code] = item
