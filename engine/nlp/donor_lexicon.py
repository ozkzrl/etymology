"""
Donör Dil Sözlüğü ve En Yakın Komşu Araması (Donor Lexicon & Nearest-Neighbour)

Alıntı keşif hattının **Katman 4** uygulaması: kelimenin 10 komşu kaynak
dildeki en yakın karşılığını IPA fonetik mesafesiyle arar.

Tasarım ölçütü::

    IPA Fonetik Mesafe (Levenshtein Edit Distance) <= 2
    Vektörel Semantik Benzerlik (FastText Cosine) >= 0.75

FastText kapsam dışıdır (gensim'in Python 3.14 tekerleği yok); semantik
doğrulama yerine **anlam örtüşmesi** ölçütü kullanılır.

Veri kaynağı: canlı çok dilli Wiktionary + ``data/seed/donor/``.
"""
from __future__ import annotations

import json
import urllib.parse
from functools import lru_cache
from typing import Any

from engine import config
from engine.logging_setup import get_logger
from engine.nlp.phonological_feature_engine import to_ipa
from engine.utils.network import fetch as http_get
from engine.utils.seed import load_seed_entries

logger = get_logger(__name__)

#: Plan dokümanındaki 10 komşu kaynak dil (Wiktionary dil kodu -> Türkçe ad).
DONOR_LANGUAGES: dict[str, str] = {
    "ar": "Arapça",
    "fa": "Farsça",
    "pal": "Pehlevice / Soğdca",
    "zh": "Çince",
    "mn": "Moğolca",
    "el": "Rumca / Yunanca",
    "hy": "Ermenice",
    "ru": "Rusça / Slav dilleri",
    "it": "İtalyanca / Venedikçe",
    "fr": "Fransızca",
}

#: Plan dokümanındaki eşik: IPA düzeyinde en fazla 2 düzenleme.
MAX_PHONETIC_DISTANCE = 2


def levenshtein(a: str, b: str) -> int:
    """Klasik düzenleme mesafesi. (Projede 3 ayrı kopyası vardı; tek kaynak.)"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ipa_distance(a: str, b: str) -> int:
    """İki biçim arasındaki IPA düzeyinde düzenleme mesafesi."""
    return levenshtein(to_ipa(a), to_ipa(b))


@lru_cache(maxsize=1)
def seed_donor_entries() -> dict[str, Any]:
    return load_seed_entries("donor/donor_etymology.json")


class DonorLexicon:
    """Komşu kaynak dillerde en yakın biçimi arar."""

    def _wiktionary_lookup(self, lang_code: str, word: str) -> str | None:
        """Verilen dilin Wiktionary'sinde kelimenin ilk tanımını arar."""
        url = (
            f"https://{lang_code}.wiktionary.org/w/api.php?action=query&format=json"
            f"&prop=extracts&explaintext=1&titles={urllib.parse.quote(word)}"
        )
        body = http_get(url, timeout=config.HTTP_TIMEOUT_SHORT, max_retries=0)
        if body is None:
            return None
        try:
            pages = json.loads(body).get("query", {}).get("pages", {})
        except (ValueError, AttributeError):
            return None
        for page in pages.values():
            if "missing" in page:
                continue
            extract = (page.get("extract") or "").strip()
            if extract:
                return extract[:200]
        return None

    def nearest_neighbours(
        self, word: str, candidate_forms: dict[str, list[str]] | None = None
    ) -> list[dict[str, Any]]:
        """
        Kelimeye fonetik olarak en yakın donör biçimlerini döndürür.

        :param candidate_forms: ``{dil_kodu: [biçim, ...]}``. Verilmezse yalnızca
            tohum donör verisi taranır (canlı sorgu için ``search_live`` kullanın).
        """
        w = (word or "").strip().lower()
        if not w:
            return []

        results: list[dict[str, Any]] = []

        # 1. Tohum donör veritabanı
        for key, entry in seed_donor_entries().items():
            form = entry.get("original_script") or key
            distance = ipa_distance(w, key)
            if distance <= MAX_PHONETIC_DISTANCE:
                results.append({
                    "donor_language": entry.get("donor_lang", "?"),
                    "origin_form": form,
                    "matched_key": key,
                    "meaning": entry.get("donor_meaning", ""),
                    "etymology": entry.get("internal_etymology", ""),
                    "phonetic_distance": distance,
                    "origin": "seed",
                })

        # 2. Sağlanan aday biçimler
        for lang_code, forms in (candidate_forms or {}).items():
            for form in forms:
                distance = ipa_distance(w, form)
                if distance <= MAX_PHONETIC_DISTANCE:
                    results.append({
                        "donor_language": DONOR_LANGUAGES.get(lang_code, lang_code),
                        "origin_form": form,
                        "matched_key": form,
                        "meaning": "",
                        "etymology": "",
                        "phonetic_distance": distance,
                        "origin": "live",
                    })

        results.sort(key=lambda r: (r["phonetic_distance"], r["donor_language"]))
        return results

    def search_live(self, word: str) -> list[dict[str, Any]]:
        """10 komşu dilin Wiktionary'sinde kelimeyi canlı arar."""
        import concurrent.futures

        w = (word or "").strip().lower()
        if not w:
            return []

        found: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as ex:
            futures = {
                ex.submit(self._wiktionary_lookup, code, w): code for code in DONOR_LANGUAGES
            }
            for fut in concurrent.futures.as_completed(futures):
                code = futures[fut]
                try:
                    extract = fut.result()
                except Exception:
                    logger.warning("Donör Wiktionary sorgusu başarısız: %s/%s", code, w, exc_info=True)
                    continue
                if extract:
                    found.append({
                        "donor_language": DONOR_LANGUAGES[code],
                        "origin_form": w,
                        "matched_key": w,
                        "meaning": extract,
                        "etymology": "",
                        "phonetic_distance": 0,
                        "origin": "live",
                    })
        found.sort(key=lambda r: r["donor_language"])
        return found
