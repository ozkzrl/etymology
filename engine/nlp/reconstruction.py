"""
Proto-Türkçe Rekonstrüksiyon Cephesi (Reconstruction Facade)

Gerçek hesaplama :mod:`engine.nlp.comparative_reconstruction` içindeki
karşılaştırmalı yöntem motorunda yapılır. Bu modül, mevcut çağrı yerlerinin
imzasını koruyan ince bir cephedir.

Not: Bu modül eskiden ``d- -> t-`` kuralını uygularken
``predictive_reconstructor`` TAM TERSİNİ (``t- -> d-``) uyguluyordu ve ikisi de
aynı aramada çalışıyordu. Ayrıca ``turkic_entries`` parametresi imzada olmasına
rağmen gövdede hiç kullanılmıyordu. Her ikisi de artık tek motordan beslenir.
"""
from __future__ import annotations

from typing import Any

from engine.nlp.comparative_reconstruction import ComparativeReconstructor
from engine.utils.morphology import NON_TURKIC_INITIAL_CONSONANTS


class ProtoTurkicReconstructor:
    def __init__(self) -> None:
        self._engine = ComparativeReconstructor()

    def reconstruct_proto_form(
        self, word: str, turkic_entries: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Akraba biçimlerden Proto-Türkçe ata biçimi türetir."""
        w = (word or "").strip().lower()

        if w and w[0] in NON_TURKIC_INITIAL_CONSONANTS:
            return {
                "word": w,
                "reconstructed_root": "",
                "is_reconstructible": False,
                "evidence_available": False,
                "confidence": None,
                "reconstruction_notes": (
                    "Söz başı ünsüzü Türkçe fonotaktiğine aykırı; Proto-Türkçe rekonstrüksiyon "
                    "uygulanmaz (alıntı kök adayı)."
                ),
            }

        return self._engine.reconstruct(w, turkic_entries)
