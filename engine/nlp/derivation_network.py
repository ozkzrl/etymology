"""
Kök Türev Ağı (Root Derivation Network)

README'nin vaat ettiği ama hiç uygulanmamış özellik::

    Kök Akraba Sözcük Ağı (cognates.py): göz -> görmek, gözlem, gözlük
    otomatik bağlar

``utils/cognates.py`` gerçekte yalnızca fetcher sonuçlarını ve ses
varyantlarını topluyordu; türetim (derivational) ağı üretecek kod yoktu.

Bu modül bir kökten üretilebilecek Türkçe türevleri **yapım ekleriyle**
oluşturur ve her adayı TDK sözlüğünde doğrular; yalnızca gerçekten var olan
kelimeler ağa girer. Böylece "gözlük" ağa girer, "gözsuz" girmez.
"""
from __future__ import annotations

import concurrent.futures
from typing import Any

from engine import config
from engine.logging_setup import get_logger
from engine.nlp.historical_morphology import HistoricalMorphologyAnalyzer
from engine.utils.orthography import to_comparison_form

logger = get_logger(__name__)

#: Üretken Türkçe yapım ekleri. (ek biçimleri, etiket, işlev)
DERIVATIONAL_SUFFIXES: list[tuple[tuple[str, ...], str, str]] = [
    (("lik", "lık", "luk", "lük"), "+lIk", "soyut ad / alet adı"),
    (("li", "lı", "lu", "lü"), "+lI", "sahiplik sıfatı"),
    (("siz", "sız", "suz", "süz"), "+sIz", "yokluk sıfatı"),
    (("ci", "cı", "cu", "cü", "çi", "çı", "çu", "çü"), "+çI", "meslek adı"),
    (("lem", "lam"), "+lAm", "eylem adı"),
    (("le", "la"), "+lA-", "addan fiil"),
    (("len", "lan"), "+lAn-", "dönüşlü fiil"),
    (("leş", "laş"), "+lAş-", "işteş fiil"),
    (("daş", "deş", "taş", "teş"), "+dAş", "ortaklık adı"),
    (("cik", "cık", "cuk", "cük"), "+cIk", "küçültme"),
    (("gi", "gı", "gu", "gü"), "-gI", "fiilden ad"),
    (("ge", "ga"), "-gA", "fiilden ad"),
    (("ek", "ak"), "-Ak", "fiilden ad"),
    (("ici", "ıcı", "ucu", "ücü"), "-IcI", "fail sıfatı"),
    (("im", "ım", "um", "üm"), "-Im", "eylem adı"),
    (("iş", "ış", "uş", "üş"), "-Iş", "eylem adı"),
    (("men", "man"), "+mAn", "meslek/unvan"),
]

#: Ünlü uyumuna göre ek seçimi için kalın/ince ünlü kümeleri
BACK = set("aıou")
FRONT = set("eiöü")


def _harmonic_variants(stem: str, surfaces: tuple[str, ...]) -> list[str]:
    """Kökün son ünlüsüne göre uyumlu ek biçimlerini seçer."""
    vowels = [c for c in stem if c in BACK | FRONT]
    if not vowels:
        return list(surfaces)
    is_back = vowels[-1] in BACK
    out = []
    for suf in surfaces:
        suf_vowels = [c for c in suf if c in BACK | FRONT]
        if not suf_vowels:
            out.append(suf)
        elif (suf_vowels[0] in BACK) == is_back:
            out.append(suf)
    return out or list(surfaces)


class DerivationNetworkBuilder:
    """Bir kökten türeyen gerçek Türkçe kelimeleri bulur."""

    def __init__(self, validator: Any | None = None):
        # Doğrulayıcı: kelimenin gerçekten var olup olmadığını söyleyen kaynak.
        self._validator = validator
        self.morphology = HistoricalMorphologyAnalyzer()

    @property
    def validator(self) -> Any:
        if self._validator is None:
            from engine.fetchers.tdk_nisanyan import TdkFetcher

            self._validator = TdkFetcher()
        return self._validator

    def candidate_derivations(self, root: str) -> list[dict[str, str]]:
        """Kökten üretilebilecek biçimsel adayları döndürür (doğrulanmamış)."""
        r = to_comparison_form(root)
        if len(r) < 2:
            return []
        candidates: list[dict[str, str]] = []
        seen: set[str] = set()
        for surfaces, label, function in DERIVATIONAL_SUFFIXES:
            for suf in _harmonic_variants(r, surfaces):
                form = r + suf
                if form in seen or form == r:
                    continue
                seen.add(form)
                candidates.append({"word": form, "suffix": label, "function": function})
        return candidates

    def build(self, root: str, *, verify: bool = True, max_candidates: int = 40) -> dict[str, Any]:
        """
        Kökün türev ağını kurar.

        :param verify: ``True`` ise her aday TDK'da doğrulanır; yalnızca
            gerçekten var olan kelimeler ağa girer. ``False`` ise biçimsel
            adaylar döner (doğrulanmamış).
        """
        r = to_comparison_form(root)
        candidates = self.candidate_derivations(r)[:max_candidates]

        if not candidates:
            return {
                "root": r,
                "evidence_available": False,
                "verified": verify,
                "derivations": [],
                "reason": "Kök türev üretimi için çok kısa.",
            }

        if not verify:
            return {
                "root": r,
                "evidence_available": True,
                "verified": False,
                "candidate_count": len(candidates),
                "derivations": candidates,
                "note": "Biçimsel adaylar; sözlükte doğrulanmadı.",
            }

        confirmed: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as ex:
            futures = {ex.submit(self._verify_word, c["word"]): c for c in candidates}
            for fut in concurrent.futures.as_completed(futures):
                cand = futures[fut]
                try:
                    meaning = fut.result()
                except Exception:
                    logger.warning("Türev doğrulaması başarısız: %s", cand["word"], exc_info=True)
                    continue
                if meaning is not None:
                    confirmed.append({**cand, "meaning": meaning, "verified": True})

        confirmed.sort(key=lambda c: c["word"])
        return {
            "root": r,
            "evidence_available": True,
            "verified": True,
            "candidate_count": len(candidates),
            "confirmed_count": len(confirmed),
            "derivations": confirmed,
        }

    def _verify_word(self, word: str) -> str | None:
        """Kelime sözlükte var mı? Varsa anlamını döndürür."""
        res = self.validator.fetch(word)
        meaning = (res.get("root", {}) or {}).get("meaning", "")
        entries = res.get("turkic_languages", [])
        if meaning:
            return meaning[:160]
        if entries:
            return (entries[0].get("meaning") or "")[:160]
        return None
