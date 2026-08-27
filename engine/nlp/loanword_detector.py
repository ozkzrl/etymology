"""
Alıntı Kelime Keşif Hattı (Loanword Detection Pipeline)

**4 katmanlı otonom alıntı keşif hattının** birleşik uygulamasıdır.

Katmanlar
---------
1. **Fonotaktik yapı ve ses ihlali analizi** — söz başı ünsüz kısıtı, ünsüz
   kümesi, ünlü uyumu, Arapça vezin, Farsça/Batı ekleri
   (:mod:`engine.utils.phonotactics`)
2. **Çapraz Türki lehçe dağılım skorlaması** — kelimenin kaç Türki dilde
   karşılığı var (:mod:`engine.nlp.cognate_alignment`)
3. **Olasılık dağılımı** — kaynak dil ailesi olasılıkları
   (:mod:`engine.nlp.loanword_classifier`)
4. **10 komşu kaynak dilde en yakın komşu araması** — IPA Levenshtein <= 2
   (:mod:`engine.nlp.donor_lexicon`)

Katman 3'ün "eğitilmiş ML sınıflandırıcı" hedefi bilinçli olarak
UYGULANMAMIŞTIR: etiketli Türkçe alıntı veri kümesi (WOLD ingest'i)
tamamlanmadan eğitilecek bir model, kalibre edilmiş kural motorundan daha
savunulabilir olmaz. Çıktıda ``method: "rule_based"`` olarak açıkça bildirilir.
"""
from __future__ import annotations

from typing import Any

from engine.logging_setup import get_logger
from engine.nlp.cognate_alignment import CognateAlignmentEngine
from engine.nlp.donor_lexicon import DonorLexicon
from engine.nlp.loanword_classifier import LoanwordClassifier

logger = get_logger(__name__)


class LoanwordDetector:
    """Dört katmanlı alıntı kelime keşif hattı."""

    def __init__(
        self,
        classifier: LoanwordClassifier | None = None,
        cognate_engine: CognateAlignmentEngine | None = None,
        donor_lexicon: DonorLexicon | None = None,
    ):
        self.classifier = classifier or LoanwordClassifier()
        self.cognate_engine = cognate_engine or CognateAlignmentEngine()
        self.donor_lexicon = donor_lexicon or DonorLexicon()

    def detect(
        self,
        word: str,
        turkic_entries: list[dict[str, Any]] | None = None,
        *,
        live_donor_search: bool = False,
    ) -> dict[str, Any]:
        """
        Kelimenin alıntı olup olmadığını dört katmanlı hattan geçirerek belirler.

        :param turkic_entries: Veri katmanından gelen gerçek Türki dil kayıtları
            (Katman 2 için zorunlu; yoksa o katman kanıt üretmez).
        :param live_donor_search: ``True`` ise Katman 4 komşu dillerin
            Wiktionary'sinde canlı arama yapar (yavaş).
        """
        w = (word or "").strip().lower()
        if not w:
            return {
                "word": "",
                "evidence_available": False,
                "verdict": None,
                "reason": "Boş sorgu.",
            }

        # Katman 2 önce: yayılım oranı Katman 3'e girdi olur
        layer2 = self.cognate_engine.evaluate_cognate_distribution(w, turkic_entries or [])
        spreading = layer2.get("spreading_ratio") if layer2.get("evidence_available") else None

        # Katman 1 + 3 (fonotaktik ihlaller ve olasılık dağılımı)
        layer13 = self.classifier.classify(w, spreading_ratio=spreading)

        # Katman 4
        neighbours = (
            self.donor_lexicon.search_live(w)
            if live_donor_search
            else self.donor_lexicon.nearest_neighbours(w)
        )
        layer4 = {
            "evidence_available": bool(neighbours),
            "match_count": len(neighbours),
            "best_match": neighbours[0] if neighbours else None,
            "matches": neighbours[:5],
        }

        verdict, confidence, rationale = self._decide(layer13, layer2, layer4)

        # Katman 4 doğrudan eşleşme bulduysa sınıflandırma ona uyar:
        # kural tabanlı olasılık tahmini, sözlük kanıtını ezemez.
        classification = layer13["classification"]
        classification_key = layer13["classification_key"]
        best = layer4.get("best_match")
        if best and best["phonetic_distance"] == 0:
            classification = f"{best['donor_language']} alıntısı (donör sözlük eşleşmesi)"
            classification_key = "donor_lexicon_match"

        return {
            "word": w,
            "method": "rule_based",
            "method_note": (
                "Kural tabanlı sezgisel hat. Katman 3'ün eğitilmiş ML modeli, "
                "etiketli veri kümesi (WOLD) olmadığı için uygulanmadı."
            ),
            "evidence_available": True,
            "verdict": verdict,
            "confidence": confidence,
            "rationale": rationale,
            "layers": {
                "layer1_phonotactics": {
                    "violations": layer13["phonotactic_violations"],
                    "violation_count": len(layer13["phonotactic_violations"]),
                },
                "layer2_cross_dialect": layer2,
                "layer3_probabilities": layer13["probabilities"],
                "layer4_donor_neighbours": layer4,
            },
            "classification": classification,
            "classification_key": classification_key,
            "rule_based_classification": layer13["classification"],
        }

    @staticmethod
    def _decide(
        layer13: dict[str, Any], layer2: dict[str, Any], layer4: dict[str, Any]
    ) -> tuple[str, float, list[str]]:
        """Katman çıktılarını tek bir karara indirger."""
        rationale: list[str] = []
        p_native = layer13["probabilities"]["p_native_turkic"]

        # Katman 4 doğrudan eşleşme en güçlü kanıttır
        best = layer4.get("best_match")
        if best and best["phonetic_distance"] == 0:
            rationale.append(
                f"Katman 4: {best['donor_language']} biçimi '{best['origin_form']}' ile birebir eşleşme"
            )
            return "loanword", 0.90, rationale
        if best and best["phonetic_distance"] <= 2:
            rationale.append(
                f"Katman 4: {best['donor_language']} '{best['origin_form']}' "
                f"(IPA mesafesi {best['phonetic_distance']})"
            )

        if layer2.get("evidence_available"):
            ratio = layer2["spreading_ratio"]
            rationale.append(
                f"Katman 2: {layer2['present_dialects_count']}/{layer2['total_language_count']} "
                f"Türki dilde karşılık (%{ratio * 100:.0f} yayılım)"
            )

        violations = layer13["phonotactic_violations"]
        if violations:
            rationale.append(f"Katman 1: {len(violations)} fonotaktik ihlal — {violations[0]}")
        else:
            rationale.append("Katman 1: fonotaktik ihlal yok")

        if p_native >= 0.70:
            return "native", round(p_native, 3), rationale
        if p_native <= 0.35:
            return "loanword", round(1.0 - p_native, 3), rationale
        return "uncertain", round(max(p_native, 1.0 - p_native), 3), rationale
