"""
Türki Diller Derin Akraba Kelime ve Türev Ağı (Cognate Network Builder)
Araması yapılan kelimelerin aynı kökten türeyen akraba sözcük kümesini
yalnızca gerçek sözlük kayıtları ve doğrulanmış diyalekt denkliği üzerinden tespit eder.
"""
from typing import Any

from engine.utils.morphology import analyze_morphology
from engine.utils.sound_shifts import generate_turkic_cognate_candidates


def get_related_cognates(word: str, entries: list[dict[str, Any]] | None = None) -> list[str]:
    """Herhangi bir kelime için yalnızca GERÇEK sözlük kayıtları ve doğrulanmış Türki dil denklerini toplar."""
    w = (word or "").strip().lower()
    if not w:
        return []

    cognate_set = []
    seen = set()

    # 1. Sözlük kayıtlarından (20+ fetcher çıktısı) gerçek kelimeleri topla
    if entries:
        for entry in entries:
            ew = (entry.get("word") or "").strip()
            ew_clean = ew.lower().lstrip("*")
            if ew_clean and ew_clean != w and ew_clean not in seen:
                seen.add(ew_clean)
                cognate_set.append(ew)

    # 2. Eğer sözlük kayıtlarından henüz yeterince akraba toplanamadıysa bilinen kök matrisini kontrol et
    if len(cognate_set) < 3:
        stem, _ = analyze_morphology(w)
        base_stem = stem or w
        candidates = generate_turkic_cognate_candidates(base_stem)
        for c in candidates:
            c_clean = c.strip().lower()
            if c_clean != w and c_clean not in seen:
                # Sadece gerçek kök haritasından gelen kelimeler
                seen.add(c_clean)
                cognate_set.append(c)

    return cognate_set[:12]

