"""
Tarihsel Ek Ağacı Çözücüsü (Historical Suffix Tree Solver)

Tarihsel morfotaktik çözümleme hedefi:

    "Kelimeyi tarihsel yapım eklerine (+gU, -ik, -gə, -ba) bölerek kelimenin
     ham kökünü ayrıştırma."

Mevcut ``utils/morphology.py`` ve ``nlp/unsupervised_morpheme_segmenter.py``
yalnızca **modern Türkiye Türkçesi** eklerini tanıyordu; plandaki Eski Türkçe
yapım ekleri hiç yoktu ve çıktı düz bir liste, "ağaç" değildi.

Bu modül tarihsel yapım eklerini tanır ve katmanlı bir türetme AĞACI kurar:

    güzellik  ->  güzel  +lIk
              ->  gö(r)-  +z   (tarihsel katman)
"""
from __future__ import annotations

from typing import Any

from engine.logging_setup import get_logger
from engine.utils.orthography import to_comparison_form

logger = get_logger(__name__)

#: Eski/Orta Türkçe yapım ekleri.
#: Her giriş: (yüzey biçimleri, etiket, işlev, tarihsel katman)
HISTORICAL_SUFFIXES: list[tuple[tuple[str, ...], str, str, str]] = [
    # --- Fiilden ad ---
    (("gu", "gü", "ğu", "ğü", "qu"), "+gU", "fiilden ad/araç adı (Eski Türkçe +gU)", "old_turkic"),
    (("g", "ğ", "k", "q"), "+G", "fiilden ad (Eski Türkçe +G)", "old_turkic"),
    (("ik", "ık", "uk", "ük"), "-Ik", "fiilden sıfat/ad (Eski Türkçe -Ik)", "old_turkic"),
    (("ge", "ga", "gə", "qa"), "-gA", "fiilden ad (Eski Türkçe -gA)", "old_turkic"),
    (("gi", "gı", "gu", "gü", "ki", "kı"), "-gI", "fiilden ad (Eski Türkçe -gI: bilgi, sevgi)", "old_turkic"),
    (("nç", "inç", "ınç", "unç", "ünç"), "-nÇ", "fiilden duygu adı (sevinç, korkunç)", "old_turkic"),
    (("gıç", "giç", "guç", "güç"), "-gIç", "fiilden araç adı (dalgıç, bilgiç)", "old_turkic"),
    (("ba", "be", "pa", "pe"), "-bA", "fiilden ad (Eski Türkçe -bA)", "old_turkic"),
    (("gan", "gen", "qan", "ken"), "-gAn", "sıfat-fiil (Eski Türkçe -gAn)", "old_turkic"),
    (("miş", "mış", "muş", "müş"), "-mIş", "geçmiş sıfat-fiil", "old_turkic"),
    (("m", "im", "ım", "um", "üm"), "-Im", "fiilden eylem adı", "old_turkic"),
    (("t", "it", "ıt", "ut", "üt"), "-It", "fiilden ad", "old_turkic"),
    (("n", "in", "ın", "un", "ün"), "-In", "fiilden ad / dönüşlü", "old_turkic"),
    (("z",), "-z", "eski ad yapım eki / ikilik (köz, teŋiz)", "old_turkic"),
    # --- Addan ad ---
    (("lik", "lık", "luk", "lük", "lig", "lıg", "lug", "lüg"), "+lIK",
     "addan soyut ad (Eski Türkçe +lIg)", "old_turkic"),
    (("çi", "çı", "çu", "çü", "ci", "cı", "cu", "cü"), "+çI", "meslek/fail adı", "old_turkic"),
    (("daş", "deş", "taş", "teş"), "+dAş", "ortaklık adı", "old_turkic"),
    (("lı", "li", "lu", "lü", "lıg", "lig"), "+lI", "addan sıfat (Eski Türkçe +lIg)", "old_turkic"),
    (("sız", "siz", "suz", "süz"), "+sIz", "yokluk sıfatı", "old_turkic"),
    (("cak", "cek", "çak", "çek"), "+çAK", "küçültme", "middle_turkic"),
    # --- Modern katman ---
    (("sal", "sel"), "+sAl", "Cumhuriyet dönemi sıfat eki", "modern"),
    (("tay", "tey"), "+tAy", "Cumhuriyet dönemi kurum adı", "modern"),
    (("men", "man"), "+mAn", "Cumhuriyet dönemi meslek eki", "modern"),
]

#: Bir kökün altına düşmemesi gereken asgari uzunluk.
MIN_STEM_LENGTH = 2
#: Azami türetme derinliği (sonsuz döngü koruması).
MAX_DEPTH = 4


class HistoricalMorphologyAnalyzer:
    """Kelimeyi tarihsel yapım eklerine göre katmanlı bir ağaca ayırır."""

    def build_tree(self, word: str) -> dict[str, Any]:
        """
        Kelimenin tarihsel türetme ağacını kurar.

        :returns: ``root`` ham kök, ``layers`` her katmanda soyulan ek,
            ``depth`` türetme derinliği.
        """
        w = to_comparison_form(word)
        if not w:
            return {
                "word": word,
                "evidence_available": False,
                "root": "",
                "layers": [],
                "depth": 0,
                "reason": "Kelime çözümlenebilir bir biçime indirgenemedi.",
            }

        layers: list[dict[str, Any]] = []
        stem = w
        for _ in range(MAX_DEPTH):
            match = self._strip_one(stem)
            if match is None:
                break
            new_stem, label, function, layer = match
            layers.append({
                "surface": stem[len(new_stem):],
                "suffix": label,
                "function": function,
                "historical_layer": layer,
                "stem_before": stem,
                "stem_after": new_stem,
            })
            stem = new_stem

        return {
            "word": word,
            "normalised": w,
            "evidence_available": bool(layers),
            "root": stem,
            "layers": layers,
            "depth": len(layers),
            "derivation_path": " + ".join([stem, *[lay["suffix"] for lay in reversed(layers)]])
            if layers
            else stem,
            "oldest_layer": layers[-1]["historical_layer"] if layers else None,
        }

    @staticmethod
    def _strip_one(stem: str) -> tuple[str, str, str, str] | None:
        """En uzun eşleşen eki soyar. Kök çok kısalırsa soymaz."""
        best: tuple[int, str, str, str, str] | None = None
        for surfaces, label, function, layer in HISTORICAL_SUFFIXES:
            for surface in surfaces:
                if not stem.endswith(surface):
                    continue
                remaining = stem[: -len(surface)]
                if len(remaining) < MIN_STEM_LENGTH:
                    continue
                cand = (len(surface), remaining, label, function, layer)
                if best is None or cand[0] > best[0]:
                    best = cand
        if best is None:
            return None
        return best[1], best[2], best[3], best[4]
