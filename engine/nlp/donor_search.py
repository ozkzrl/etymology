"""
Donör (Kaynak Dil) Arama Motoru — Katman 4

Alıntı keşif hattının **Katman 4** uygulaması: kelimenin komşu kaynak
dillerdeki en yakın karşılığını arar.

Yeniden yazılma gerekçesi
-------------------------
Önceki uygulama eşleşme bulamadığında ``donor_language`` alanına şu **sahte
durum metnini** yazıyordu::

    "10 Komşu Dilde Canlı Taranıyor (Arapça, Farsça, Grekçe, Moğolca, vb.)"

Bu bir dil adı değil, bir ilerleme mesajıydı; JSON çıktısında ve web panelinde
sanki bir bulguymuş gibi görünüyordu. Artık eşleşme yoksa ``found_match: False``
ve ``donor_language: None`` döner.
"""
from __future__ import annotations

from typing import Any

from engine.logging_setup import get_logger
from engine.nlp.donor_etymology_database import DeepDonorEtymologyDatabase

logger = get_logger(__name__)


class DonorSearchEngine:
    def __init__(self, donor_db: Any | None = None):
        self.donor_db = donor_db or DeepDonorEtymologyDatabase()

    def search_donor_neighbors(self, word: str) -> dict[str, Any]:
        w = (word or "").strip().lower()
        if not w:
            return {"word": w, "found_match": False, "donor_language": None,
                    "origin_form": None, "donor_meaning": None,
                    "reason": "Boş sorgu."}

        res = self.donor_db.lookup(w)
        if res:
            return {
                "word": w,
                "found_match": True,
                "donor_language": res["donor_language"],
                "origin_form": res["origin_form"],
                "donor_meaning": res["historical_meaning"],
                "evidence_source": res.get("source", "donör veritabanı"),
            }

        logger.debug("Donör eşleşmesi yok: %s", w)
        return {
            "word": w,
            "found_match": False,
            "donor_language": None,
            "origin_form": None,
            "donor_meaning": None,
            "reason": "Komşu kaynak dillerde eşleşme bulunamadı.",
        }
