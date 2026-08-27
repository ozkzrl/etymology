"""
Zeki Diyalekt ve Fonetik Varyant Türetici (Dynamic Phonetic Variant Generator)
Araması yapılan kelimenin tüm Türki dillerdeki fonetik ünsüz/ünlü değişim varyantlarını
herhangi bir sabit kelime haritası kullanmaksızın %100 jenerik ve algoritma tabanlı hesaplar.
"""

from engine.utils.sound_shifts import generate_turkic_cognate_candidates


def generate_dynamic_phonetic_variants(word: str) -> list[str]:
    """Tüm Türki diller arası ses denkliği ve transkripsiyon kurallarıyla tam jenerik fonetik varyant kümesi üretir."""
    w = (word or "").strip().lower()
    if not w:
        return []

    # Jenerik Türki ses kanunlarından %100 otonom varyant üretimi
    candidates = generate_turkic_cognate_candidates(w)

    # w'nun kendisi her zaman listenin başında yer alsın
    if w in candidates:
        candidates.remove(w)
    candidates.insert(0, w)

    return candidates
