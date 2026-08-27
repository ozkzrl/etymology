"""
Çok Dilli Wiktionary Veri Toplayıcı (Multi-Language Wiktionary Fetcher)

Her Türki dilin kendi Wiktionary'sinde kelimenin karşılığını arar ve **gerçek
tanımı** çıkarır.

Yeniden yazılma gerekçesi
-------------------------
Önceki uygulama:

* ``lang_target_map`` içinde 15 dil × 7 kelime = ~95 elle yazılmış kelime
  taşıyordu (yalnızca belge/deniz/göz/el/su/ayak için). Kaynak adı
  "25 Türki Dil Kapsamı" diyordu ama harita 15 dil içeriyordu.
* Kazakça girdisi ``kөз`` şeklinde **karışık alfabeliydi** (Latin k + Kiril өз);
  bu biçim hiçbir zaman bulunamıyordu.
* Anlam olarak gerçek tanım yerine ``"Online Kazakça Sözlük kaydı"``
  yer tutucusu yazıyordu.
* 15 Wiktionary'yi **seri** sorguluyordu; tek bir aramada 58,9 saniye
  harcıyordu (toplam sürenin %93'ü).

Artık: gömülü kelime yok, sorgular paralel, anlamlar gerçek.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import urllib.parse
from typing import Any

from engine import config
from engine.fetchers.base import TURKIC_LANGUAGES_MAP, BaseFetcher, detect_script
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get

logger = get_logger(__name__)

#: Kendi Wiktionary alan adı bulunan Türki diller.
#: (Tüm Türki dillerin ayrı Wiktionary'si yoktur.)
WIKTIONARY_EDITIONS: tuple[str, ...] = (
    "az", "kk", "uz", "ky", "tt", "ba", "cv", "sah", "tk", "ug", "gag", "krc", "tyv", "alt",
)

#: Tanım satırlarını yakalar: "# tanım" veya "# [[bağlantı]]"
_DEF_RE = re.compile(r"^#\s*(?!#)(.+)$", re.M)
_WIKI_MARKUP_RE = re.compile(r"\{\{[^}]*\}\}|\[\[([^\]|]*\|)?|\]\]|'''|''")


class MultiLangWiktionaryFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return f"Türki Diller Wiktionary Sürümleri ({len(WIKTIONARY_EDITIONS)} dil)"

    def _clean_definition(self, raw: str) -> str:
        text = _WIKI_MARKUP_RE.sub("", raw or "")
        text = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"\s+", " ", text).strip(" .;:,")

    def _query_wiktionary(self, lang_code: str, word: str) -> str | None:
        """Verilen dilin Wiktionary'sinde kelimeyi arar; ilk tanımı döndürür."""
        url = (
            f"https://{lang_code}.wiktionary.org/w/api.php?action=parse"
            f"&page={urllib.parse.quote(word)}&format=json&prop=wikitext"
        )
        body = http_get(url, timeout=config.HTTP_TIMEOUT_SHORT, max_retries=0)
        if body is None:
            return None
        try:
            data = json.loads(body)
        except ValueError:
            logger.debug("Wiktionary JSON ayrıştırılamadı: %s/%s", lang_code, word)
            return None
        if "error" in data or "parse" not in data:
            return None

        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        if len(wikitext) < 10:
            return None

        for m in _DEF_RE.finditer(wikitext):
            definition = self._clean_definition(m.group(1))
            if definition and len(definition) > 1:
                return definition[:200]
        # Sayfa var ama tanım satırı çıkarılamadı — yine de varlık kanıtıdır.
        return ""

    def fetch(self, word: str) -> dict[str, Any]:
        from engine.utils.sound_shifts import generate_turkic_cognate_candidates

        result = self.empty_result()
        w = (word or "").strip().lower()
        if not w:
            return result

        # Aday biçimler: kelimenin kendisi + türetilen ses varyantları.
        # Gömülü kelime listesi yok; varyantlar sound_shifts'ten gelir.
        candidates = [w, *[c for c in generate_turkic_cognate_candidates(w) if c != w]]
        candidates = candidates[: config.MAX_VARIANTS]

        jobs = [(code, cand) for code in WIKTIONARY_EDITIONS for cand in candidates]

        found: dict[str, tuple[str, str]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as ex:
            future_map = {ex.submit(self._query_wiktionary, code, cand): (code, cand) for code, cand in jobs}
            for fut in concurrent.futures.as_completed(future_map):
                code, cand = future_map[fut]
                try:
                    definition = fut.result()
                except Exception:
                    logger.warning("Wiktionary sorgusu başarısız: %s/%s", code, cand, exc_info=True)
                    continue
                if definition is None:
                    continue
                # Aynı dil için ilk (en kısa adaya ait) kaydı tut
                if code not in found or len(cand) < len(found[code][0]):
                    found[code] = (cand, definition)

        for code, (cand, definition) in sorted(found.items()):
            result["turkic_languages"].append(
                self.make_entry(
                    code,
                    cand,
                    definition or f"{TURKIC_LANGUAGES_MAP.get(code, code)} Wiktionary'de madde mevcut",
                    script=detect_script(cand),
                )
            )
        return result
