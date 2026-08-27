"""
Donör Etimoloji Sorgulayıcı (Donor Etymology Lookup)

Kelimenin bilinen bir alıntı olup olmadığını donör sözlüğünden sorgular.

Düzeltilen sorunlar
-------------------
* **Gizli ağ çağrısı**: ``lookup()`` bir sözlük araması gibi görünmesine
  rağmen her çağrıda canlı Wiktionary API'sine gidiyordu. Tek bir aramada
  bu metot 4 kez çağrıldığı için "saf NLP" katmanı 4 ağ isteği yapıyor ve
  tek sahte fetcher'la yapılan arama bile 6,5 saniye sürüyordu. Canlı sorgu
  artık ``allow_live`` ile AÇIKÇA istenmelidir.
* **Yanlış docstring**: "Koda elle yazılmış hiçbir sabit kelime barındırmaz"
  diyordu; hemen ardından 10 kelimelik gömülü sözlüğü import ediyordu.
  Sözlük artık ``data/seed/donor/`` altındadır ve tohum veri olarak
  etiketlenir.
* **Belirsiz donör dili**: Canlı sorgu eşleştiğinde ``donor_language``
  alanına "Canlı Wiktionary / Donör Dil Sorgusu" yazılıyordu — bu bir dil adı
  değildi. Artık tespit edilen gerçek dil adı yazılır.
"""
from __future__ import annotations

import re
from typing import Any

from engine.logging_setup import get_logger
from engine.utils.seed import load_seed_entries

logger = get_logger(__name__)

SEED_PATH = "donor/donor_etymology.json"

#: Wiktionary etimoloji metninde donör dili tespit etmek için desenler.
DONOR_LANGUAGE_PATTERNS: list[tuple[str, str]] = [
    (r"\bArabic\b|\bArapça\b", "Arapça"),
    (r"\bPersian\b|\bFarsça\b", "Farsça"),
    (r"\bAncient Greek\b|\bGreek\b|\bGrekçe\b|\bYunanca\b", "Grekçe"),
    (r"\bFrench\b|\bFransızca\b", "Fransızca"),
    (r"\bItalian\b|\bİtalyanca\b", "İtalyanca"),
    (r"\bArmenian\b|\bErmenice\b", "Ermenice"),
    (r"\bLatin\b|\bLatince\b", "Latince"),
    (r"\bRussian\b|\bRusça\b", "Rusça"),
    (r"\bMongolian\b|\bMoğolca\b", "Moğolca"),
    (r"\bSogdian\b|\bSoğdca\b", "Soğdca"),
    (r"\bChinese\b|\bÇince\b", "Çince"),
]


def _detect_donor_language(text: str) -> str | None:
    for pattern, name in DONOR_LANGUAGE_PATTERNS:
        if re.search(pattern, text, re.I):
            return name
    return None


class DeepDonorEtymologyDatabase:
    """Donör sözlüğünden alıntı kelime kaydı arar."""

    def __init__(self, allow_live: bool = False):
        """
        :param allow_live: ``True`` ise tohum sözlükte bulunamayan kelimeler
            için canlı Wiktionary sorgusu yapılır. Varsayılan ``False``;
            bu metot NLP boru hattında sık çağrıldığı için canlı sorgu
            varsayılan olmamalıdır.
        """
        self.allow_live = allow_live

    @property
    def entries(self) -> dict[str, Any]:
        return load_seed_entries(SEED_PATH)

    def lookup(self, word: str) -> dict[str, Any] | None:
        """Kelimenin donör kaydını döndürür; bulunamazsa ``None``."""
        w = (word or "").strip().lower()
        if not w:
            return None

        entry = self.entries.get(w)
        if entry:
            return {
                "word": w,
                "found": True,
                "donor_language": entry["donor_lang"],
                "origin_form": entry["original_script"],
                "etymology": entry.get("internal_etymology", ""),
                "historical_meaning": (
                    f"Kaynak anlamı: {entry.get('donor_meaning', '')} | "
                    f"Geçiş yörüngesi: {entry.get('trajectory', '')}"
                ),
                "source": "tohum donör sözlüğü",
                "origin": "seed",
            }

        if not self.allow_live:
            return None
        return self._live_lookup(w)

    def _live_lookup(self, w: str) -> dict[str, Any] | None:
        """Canlı Wiktionary sorgusu — yalnızca ``allow_live=True`` iken."""
        from engine.llm.advanced_tools import tool_wiktionary_multilingual_api

        try:
            res = tool_wiktionary_multilingual_api(w)
        except Exception:
            logger.warning("Canlı donör sorgusu başarısız: %s", w, exc_info=True)
            return None

        if not (res.get("raw_found") and res.get("api_summary")):
            return None

        summary = " ".join(res["api_summary"])
        donor = _detect_donor_language(summary)
        if not donor:
            return None

        return {
            "word": w,
            "found": True,
            "donor_language": donor,
            "origin_form": w,
            "etymology": summary[:300],
            "historical_meaning": f"Canlı Wiktionary etimoloji kaydı: {summary[:150]}",
            "source": "canlı Wiktionary",
            "origin": "live",
        }
