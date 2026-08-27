"""
Alıntı Kelime Sınıflandırıcısı — Katman 1 + 2 (Loanword Classifier)

Alıntı keşif hattının **Katman 1** (fonotaktik ihlal analizi) ve
**Katman 2** (çapraz lehçe yayılımı) uygulamasıdır.

Düzeltilen kritik hata
----------------------
Önceki sürümde ünlü uyumsuzluğu gibi ihlaller ``score_native``'i düşürüyor ama
**hiçbir alıntı kovasına puan eklemiyordu**. Olasılık dağılımı toplam skora
bölünerek normalize edildiği için pay ve payda birlikte küçülüyor,
``p_native`` yeniden **1.0**'a çıkıyordu. Sonuç::

    kitap      -> "Asli Öz Türkçe"  p_native = 1.0   (1 ihlal tespit edilmiş!)
    televizyon -> "Asli Öz Türkçe"  p_native = 1.0
    müdür      -> "Asli Öz Türkçe"  p_native = 1.0
    kalem      -> "Asli Öz Türkçe"  p_native = 1.0

Artık her ihlal, hangi kaynak dil ailesini işaret ediyorsa O KOVAYA puan
ekler; öz Türkçe kovası yalnızca ihlal yokluğundan beslenir.

Ayrıca ``score_greek_latin`` eskiden yalnızca ``score_arabic_persian`` ile
BİRLİKTE artıyordu; bu yüzden ``p_greek_latin > p_arabic_persian`` dalı hiçbir
zaman doğru olamıyor (ölü kod), ``==`` dalı ise her Arapça alıntıyı
"Akdeniz/Ermenice/Grekçe" diye sınıflandırıyordu. Grekçe/Latince artık
bağımsız sinyallerden beslenir.
"""
from __future__ import annotations

from typing import Any

from engine.logging_setup import get_logger
from engine.utils.phonotactics import (
    PERSIAN_SUFFIXES,
    STRICT_NON_TURKIC_INITIALS,
    WEAK_NON_TURKIC_INITIALS,
    WESTERN_SUFFIXES,
    has_vowel_harmony,
    initial_cluster_violation,
    match_arabic_pattern,
    match_greek_latin_pattern,
    match_suffix,
)

logger = get_logger(__name__)

#: Söz başı ünsüzlerinin işaret ettiği kaynak dil aileleri.
INITIAL_HINTS: dict[str, tuple[str, ...]] = {
    "f": ("arabic_persian", "western"),
    "h": ("arabic_persian", "greek_latin"),
    "p": ("arabic_persian", "greek_latin", "western"),
    "v": ("arabic_persian", "western"),
    "j": ("western",),
    "z": ("arabic_persian", "greek_latin"),
    "c": ("arabic_persian",),
    "ğ": ("arabic_persian",),
    "r": ("arabic_persian", "western"),
    "l": ("arabic_persian", "western"),
    "m": ("arabic_persian",),
    "n": ("arabic_persian",),
}

CLASSIFICATION_LABELS = {
    "native": "Asli Öz Türkçe (Native Turkic)",
    "arabic_persian": "Arapça / Farsça Alıntısı (Doğu Alıntısı)",
    "greek_latin": "Grekçe / Bizans / Latince / Ermenice Alıntısı",
    "western": "Batı Dilleri Alıntısı (Fransızca / İngilizce / İtalyanca)",
}

#: p_native bu değerin üzerindeyse "asli Öz Türkçe" sayılır.
NATIVE_THRESHOLD = 0.55


class LoanwordClassifier:
    @staticmethod
    def _is_native_compound(word: str) -> bool:
        """Kelime Türkçe bir bileşik mi? (ünlü uyumu istisnası için)"""
        from engine.nlp.neologism_detector import NeologismDetector

        res = NeologismDetector().detect(word)
        return bool(res and res.get("components"))

    def classify(
        self, word: str, spreading_ratio: float | None = None
    ) -> dict[str, Any]:
        """
        Kelimenin kaynak dil ailesi olasılık dağılımını hesaplar.

        :param spreading_ratio: Katman 2'den gelen çapraz Türki lehçe yayılım
            oranı (0.0–1.0). Verilirse öz Türkçe kanıtını güçlendirir/zayıflatır.
            Bu, plan dokümanının Katman 1 + Katman 2 birleşimidir.
        """
        w = (word or "").strip().lower()
        if not w:
            return {
                "word": "",
                "classification": None,
                "evidence_available": False,
                "probabilities": {},
                "phonotactic_violations": [],
                "reason": "Boş sorgu.",
            }

        # İki AYRI hesap yapılır:
        #   1) nativeness  : kelime Öz Türkçe fonotaktiğine ne kadar uyuyor?
        #   2) donor_scores: uymuyorsa hangi kaynak dil ailesini işaret ediyor?
        # Eskiden ikisi tek havuzda toplanıyordu; ihlal puanı aileler arasında
        # bölününce seyreliyor ve p_native yeniden 1.0'a dönüyordu.
        nativeness = 1.0
        donor_scores = {"arabic_persian": 0.0, "greek_latin": 0.0, "western": 0.0}
        violations: list[str] = []

        def add(families: tuple[str, ...] | str, points: float) -> None:
            fams = (families,) if isinstance(families, str) else families
            share = points / len(fams)
            for fam in fams:
                donor_scores[fam] += share

        # --- Katman 1a: söz başı ünsüz kısıtı ---
        first = w[0]
        if first in STRICT_NON_TURKIC_INITIALS:
            nativeness -= 0.55
            add(INITIAL_HINTS.get(first, ("arabic_persian",)), 5.0)
            violations.append(f"Söz başı '{first}-' Öz Türkçede bulunmaz")
        elif first in WEAK_NON_TURKIC_INITIALS:
            nativeness -= 0.25
            add(INITIAL_HINTS.get(first, ("arabic_persian",)), 2.5)
            violations.append(f"Söz başı '{first}-' Öz Türkçede alışılmadıktır")

        # --- Katman 1b: söz başı ünsüz kümesi ---
        has_cluster, cluster_reason = initial_cluster_violation(w)
        if has_cluster:
            nativeness -= 0.60
            add("western", 6.0)
            violations.append(cluster_reason)

        # --- Katman 1c: büyük ünlü uyumu ---
        # Öz Türkçe kelimeler ünlü uyumuna uyar; ihlal GÜÇLÜ alıntı kanıtıdır.
        # İSTİSNA: bileşik kelimeler (bilgi+sayar, baş+öğretmen) uyumu öğe
        # sınırında doğal olarak bozar; bu bir alıntı göstergesi değildir.
        is_compound = self._is_native_compound(w)
        if is_compound:
            violations.append("Bileşik yapı: ünlü uyumu öğe sınırında bozulur (alıntı göstergesi değil)")
        if not is_compound and not has_vowel_harmony(w):
            nativeness -= 0.50
            add(("arabic_persian", "western", "greek_latin"), 3.0)
            violations.append("Büyük ünlü uyumu ihlali")

        # --- Katman 1d: Arapça vezin ---
        arabic = match_arabic_pattern(w)
        if arabic:
            nativeness -= 0.35
            add("arabic_persian", 6.0)
            violations.append(f"Arapça {arabic}")

        # --- Katman 1e: Farsça yapım eki ---
        persian = match_suffix(w, PERSIAN_SUFFIXES)
        if persian:
            nativeness -= 0.35
            add("arabic_persian", 5.0)
            violations.append(f"Farsça {persian}")

        # --- Katman 1f: Batı dili eki ---
        western = match_suffix(w, WESTERN_SUFFIXES)
        if western:
            nativeness -= 0.50
            add("western", 6.5)
            violations.append(f"Batı dili {western}")

        # --- Katman 1g: Grek/Latin kalıbı ---
        greek = match_greek_latin_pattern(w)
        if greek:
            nativeness -= 0.25
            add("greek_latin", 4.0)
            violations.append(f"Grekçe/Latince {greek}")

        # --- Katman 2: çapraz Türki lehçe yayılımı ---
        spread_note = None
        if spreading_ratio is not None:
            if spreading_ratio >= 0.40:
                nativeness += 0.35 * spreading_ratio
                spread_note = f"Geniş çapraz-lehçe yayılımı (%{spreading_ratio * 100:.0f}) öz Türkçe kanıtı"
            elif spreading_ratio <= 0.12:
                nativeness -= 0.15
                add(("arabic_persian", "western", "greek_latin"), 1.5)
                spread_note = f"Dar yayılım (%{spreading_ratio * 100:.0f}) alıntı göstergesi"

        p_native = round(min(1.0, max(0.02, nativeness)), 3)
        loan_mass = round(1.0 - p_native, 3)

        donor_total = sum(donor_scores.values())
        if donor_total > 0:
            probabilities = {
                k: round(loan_mass * v / donor_total, 3) for k, v in donor_scores.items()
            }
        else:
            probabilities = dict.fromkeys(donor_scores, round(loan_mass / 3, 3))
        probabilities["native"] = p_native

        if p_native >= NATIVE_THRESHOLD:
            best = "native"
        else:
            best = max(donor_scores, key=lambda k: donor_scores[k]) if donor_total > 0 else "native"

        return {
            "word": w,
            "classification": CLASSIFICATION_LABELS[best],
            "classification_key": best,
            "evidence_available": True,
            "probabilities": {
                "p_native_turkic": probabilities["native"],
                "p_arabic_persian": probabilities["arabic_persian"],
                "p_greek_latin": probabilities["greek_latin"],
                "p_western": probabilities["western"],
            },
            "phonotactic_violations": violations,
            "cross_dialect_note": spread_note,
        }
