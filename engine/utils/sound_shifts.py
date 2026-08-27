"""
Türki Diller Ses Denkliği ve Varyant Üretici (Turkic Sound Shift & Cognate Generator)

Bir kelimenin diğer Türki dillerde alabileceği biçimleri, Türki diller arası
düzenli ses denkliklerine göre üretir. Üretilen varyantlar arama sorgusu olarak
kullanılır.

Düzeltilen sorunlar
-------------------
* ``set`` yinelemesi ``PYTHONHASHSEED``'e bağlı olduğu için varyant listesi her
  çalıştırmada farklı sıralanıyordu; ``MAX_VARIANTS`` ile kırpıldığında her
  çalıştırmada FARKLI varyantlar aranıyordu. Artık sıralı döner.
* ``(r'z$', 'z')`` kuralı kendini kendine dönüştüren bir no-op'tu.
* Ünlü kuralları ``re.sub`` ile TÜM eşleşmeleri değiştiriyordu
  ("deneme" -> "dinimi"); artık yalnızca ilk eşleşme değişir.
* Elle yazılmış 5 kelimelik "yaygın kök matrisi" (``belg``/``deniz``/``su``/
  ``göz``/``tetik``) **substring** eşleşmesi yapıyordu: ``usul``, ``masum``,
  ``kusur``, ``susmak`` gibi her kelimeye 9 sahte "su" varyantı ekleniyor ve
  18 fetcher'a boşa istek atılıyordu. Bu matris ``data/seed/cognate_roots.json``
  dosyasına taşındı ve yalnızca TAM kök eşleşmesinde uygulanır.
"""
from __future__ import annotations

import re
from functools import lru_cache

from engine.logging_setup import get_logger

logger = get_logger(__name__)

# Türki diller arası düzenli ses denklikleri.
# (desen, karşılık, yalnızca_ilk_eşleşme)
SOUND_SHIFT_RULES: list[tuple[str, str, bool]] = [
    # Söz başı ünsüz denklikleri
    (r"^d", "t", True), (r"^t", "d", True),
    (r"^b", "m", True), (r"^b", "p", True), (r"^b", "v", True),
    (r"^g", "k", True), (r"^k", "g", True),
    (r"^y", "c", True), (r"^y", "j", True), (r"^y", "ç", True),
    # Söz sonu z ~ s ~ ş ~ r (Oğur/Çuvaş rotasizmi dâhil)
    (r"z$", "s", True), (r"z$", "ş", True), (r"z$", "r", True),
    # Ünlü denklikleri — yalnızca İLK eşleşme değişir
    (r"e", "i", True), (r"i", "e", True), (r"e", "ə", True), (r"e", "ä", True),
    (r"o", "u", True), (r"u", "o", True), (r"ö", "ü", True), (r"ü", "ö", True),
    # Ünsüz yumuşaması
    (r"g", "ğ", True), (r"g", "w", True), (r"g", "v", True),
]

CYRILLIC_TRANSCRIPTIONS = {
    "a": "а", "b": "б", "c": "дж", "ç": "ч", "d": "д", "e": "е", "f": "ф", "g": "г", "ğ": "ғ",
    "h": "х", "ı": "ы", "i": "и", "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "ñ": "ң",
    "o": "о", "ö": "ө", "p": "п", "r": "р", "s": "с", "ş": "ш", "t": "т", "u": "у", "ü": "ү",
    "v": "в", "y": "й", "z": "з", "ə": "ә", "ä": "ә",
}

SUFFIX_VARIANTS: dict[str, list[str]] = {
    "gi": ["g", "ğ", "gə", "ge", "gü", "ik", "ig", "iğ"],
    "ge": ["g", "ğ", "gə", "gi", "gü", "ik", "ig", "iğ"],
    "lik": ["lıq", "lık", "ліқ", "лык", "лық"],
    "lık": ["lıq", "lik", "ліқ", "лык", "лық"],
}


@lru_cache(maxsize=1)
def load_cognate_roots() -> dict[str, list[str]]:
    """
    Elle derlenmiş kök -> bilinen lehçe biçimleri eşlemesi (seed veri).

    Dosya yoksa boş sözlük döner; motor çalışmaya devam eder.
    """
    from engine.utils.seed import load_seed_entries

    return {k: list(v) for k, v in load_seed_entries("cognate_roots.json").items()}


def _apply_rule(word: str, pattern: str, replacement: str, first_only: bool) -> str:
    return re.sub(pattern, replacement, word, count=1 if first_only else 0)


def generate_turkic_cognate_candidates(word: str) -> list[str]:
    """
    Kelimenin Türki dillerdeki olası biçimlerini üretir.

    Dönüş her zaman sıralıdır (deterministik).
    """
    w = (word or "").strip().lower()
    if not w:
        return []

    candidates: set[str] = {w}

    # 1. Ek varyasyonları
    for suffix, replacements in SUFFIX_VARIANTS.items():
        if w.endswith(suffix) and len(w) > len(suffix):
            stem = w[: -len(suffix)]
            candidates.update(stem + r for r in replacements)
            break

    # 2. Düzenli ses denklikleri
    for pattern, replacement, first_only in SOUND_SHIFT_RULES:
        if re.search(pattern, w):
            mod = _apply_rule(w, pattern, replacement, first_only)
            if mod != w:
                candidates.add(mod)

    # 3. Kiril transkripsiyonu
    for item in list(candidates):
        candidates.add("".join(CYRILLIC_TRANSCRIPTIONS.get(ch, ch) for ch in item))

    # 4. Bilinen kök biçimleri — TAM eşleşme (eskiden substring idi)
    roots = load_cognate_roots()
    for root, forms in roots.items():
        if w == root or w.startswith(root + "-"):
            candidates.update(forms)
            break

    return sorted(candidates)
