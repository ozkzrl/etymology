"""
Tanıklanmamış Kelimeler İçin Rekonstrüksiyon Cephesi

Sözlüklerde etimolojik çözümü bulunmayan kelimeler için ata biçim türetir.
Hesaplama :mod:`engine.nlp.comparative_reconstruction` motorunda yapılır.

Not: Bu modül eskiden akraba listesini yalnızca ``len()`` almak için kullanıp
içeriğini atıyor, güven skorunu ise akraba SAYISINA göre sabit ``0.88`` /
``0.75`` olarak veriyordu. Artık ata biçim gerçekten akraba biçimlerden
türetilir ve güven skoru kanıttan hesaplanır.
"""
from __future__ import annotations

from typing import Any

from engine.nlp.comparative_reconstruction import ComparativeReconstructor


class PredictiveReconstructor:
    def __init__(self) -> None:
        self._engine = ComparativeReconstructor()

    def reconstruct_unattested_proto_form(
        self, word: str, cognate_entries: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        res = self._engine.reconstruct(word, cognate_entries)
        # Geriye dönük uyumlu anahtar adları
        return {
            "target_word": res.get("word", word),
            "reconstructed_proto_form": res.get("reconstructed_root", ""),
            "reconstruction_confidence": res.get("confidence"),
            "evidence_available": res.get("evidence_available", False),
            "witness_count": res.get("witness_count", 0),
            "applied_historical_rules": res.get("applied_correspondences", []),
            "reconstruction_notes": res.get("reconstruction_notes", ""),
        }
