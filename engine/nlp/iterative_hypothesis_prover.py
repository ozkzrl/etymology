"""
Tanıklanmamış Kelimeler İçin Hipotez Üretici (Unattested Word Hypothesis Prover)

Sözlüklerde etimolojik kaydı bulunmayan kelimeler için ata biçim önerisi
üretir ve A-HVP protokolünden geçirir.

Düzeltilen sorun
----------------
Önceki sürüm **her kelimeye mutlaka bir hipotez** üretiyordu: akraba tanığı
olmasa bile ``*<kelime>`` biçiminde bir "Proto-Türkçe kök" uyduruyor,
0.82 / 0.88 sabit güven skoru atıyordu. ``bilgisayar`` (1970'ler TDK
türetmesi) için ``*bilgisayar`` gibi var olmayan bir ata biçim üretiliyordu.

Artık kanıt yoksa hipotez ÜRETİLMEZ; ``hypothesis_available: False`` döner.
"""
from __future__ import annotations

from typing import Any

from engine.logging_setup import get_logger
from engine.nlp.historical_attestation_verifier import HistoricalAttestationVerifier
from engine.nlp.hypothesis_validation_protocol import HypothesisValidationProtocol
from engine.nlp.neologism_detector import NeologismDetector
from engine.nlp.predictive_reconstructor import PredictiveReconstructor
from engine.nlp.unsupervised_morpheme_segmenter import UnsupervisedMorphemeSegmenter
from engine.utils.phonotactics import initial_consonant_violation

logger = get_logger(__name__)


class IterativeHypothesisProver:
    """Kanıta dayalı hipotez üretimi; kanıt yoksa üretmez."""

    def __init__(self) -> None:
        self.segmenter = UnsupervisedMorphemeSegmenter()
        self.reconstructor = PredictiveReconstructor()
        self.validator_protocol = HypothesisValidationProtocol()
        self.attestation_verifier = HistoricalAttestationVerifier()
        self.neologism_detector = NeologismDetector()

    def prove_unattested_word(
        self, word: str, turkic_entries: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        w = (word or "").strip().lower()
        entries = turkic_entries or []

        morph_res = self.segmenter.segment_morphemes(w)
        stem = morph_res.get("stem") or w
        recon_res = self.reconstructor.reconstruct_unattested_proto_form(stem, entries)
        attestation = self.attestation_verifier.verify_attestation(w, entries)
        neologism = self.neologism_detector.detect(w)

        hypothesis = self._build_hypothesis(w, stem, recon_res, neologism)
        if hypothesis is None:
            logger.debug("Kanıt yetersiz, hipotez üretilmedi: %s", w)
            return {
                "query_word": w,
                "hypothesis_available": False,
                "morphological_segmentation": morph_res,
                "predictive_reconstruction": recon_res,
                "proven_hypothesis": None,
                "validation_report": None,
                "attestation": attestation,
                "reason": (
                    "Ata biçim türetmek için yeterli akraba tanığı yok ve kelime "
                    "bilinen bir türetme kalıbına uymuyor. Hipotez ÜRETİLMEDİ."
                ),
            }

        val_report = self.validator_protocol.validate_hypothesis(w, hypothesis, attestation, entries)
        hypothesis["validation_report"] = val_report
        hypothesis["confidence_score"] = val_report["final_confidence_score"]

        return {
            "query_word": w,
            "hypothesis_available": True,
            "morphological_segmentation": morph_res,
            "predictive_reconstruction": recon_res,
            "proven_hypothesis": hypothesis,
            "validation_report": val_report,
            "attestation": attestation,
        }

    @staticmethod
    def _build_hypothesis(
        w: str, stem: str, recon_res: dict[str, Any], neologism: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Kanıt varsa hipotez kurar; yoksa ``None`` döner."""
        # 1. Modern türetme (neologizm / bileşik) — ata biçim ARANMAZ
        if neologism and neologism.get("is_neologism"):
            return {
                "hypothesis_type": "Modern Türkçe türetme (Cumhuriyet dönemi)",
                "donor_language": "Türkçe (modern türetme)",
                "origin_form": "+".join(neologism.get("components", [])) or stem,
                "proof_summary": neologism.get("etymology_details", ""),
                "historical_meaning": "",
                "modern_meaning": "",
                "is_modern_derivation": True,
            }

        # 2. Karşılaştırmalı yöntemle türetilmiş ata biçim
        if recon_res.get("evidence_available") and recon_res.get("reconstructed_proto_form"):
            return {
                "hypothesis_type": "Karşılaştırmalı yöntemle önerilen Proto-Türkçe kök",
                "donor_language": "Proto-Türkçe",
                "origin_form": recon_res["reconstructed_proto_form"],
                "proof_summary": recon_res.get("reconstruction_notes", ""),
                "historical_meaning": "",
                "modern_meaning": "",
                "witness_count": recon_res.get("witness_count", 0),
                "applied_correspondences": recon_res.get("applied_historical_rules", []),
            }

        # 3. Fonotaktik ihlal — alıntı ADAYI, ama kaynak dil bilinmiyor
        violated, reason = initial_consonant_violation(w)
        if violated:
            return {
                "hypothesis_type": "Alıntı adayı (kaynak dil belirlenemedi)",
                "donor_language": "",
                "origin_form": w,
                "proof_summary": f"{reason}. Kaynak dil tespiti için donör sözlük kanıtı gerekiyor.",
                "historical_meaning": "",
                "modern_meaning": "",
                "is_loan_candidate": True,
            }

        # 4. Kanıt yok — hipotez UYDURULMAZ
        return None
