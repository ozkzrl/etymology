"""
Etimolojik Hipotez Kurucu (Etymological Hypothesis Engine)

Kelime için en iyi desteklenen etimoloji hipotezini kurar ve A-HVP
protokolünden geçirir.

Düzeltilen sorun
----------------
Önceki sürümde dört hipotez dalının dördü de **sabit güven skoru** taşıyordu
(0.99 / 0.98 / 0.85 / 0.90) ve son ``else`` dalı her kelimeye mutlaka bir
"Asli Öz Türkçe Köken Hipotezi" kuruyordu — akraba tanığı olmasa bile.
Bu yüzden ``bilgisayar`` için ``*bilgisayar``, ``zzzqx`` için ``*zzzqx``
gibi var olmayan ata biçimler üretiliyordu.

Sabit skorlar zaten A-HVP çıktısıyla eziliyordu (yani ölü koddu) ama kod
okuyanı ve JSON tüketicisini yanıltıyordu. Artık hipotez yalnızca kanıt
varsa kurulur ve tek güven kaynağı A-HVP'dir.
"""
from __future__ import annotations

from typing import Any

from engine.logging_setup import get_logger
from engine.nlp.comparative_reconstruction import ComparativeReconstructor
from engine.nlp.donor_etymology_database import DeepDonorEtymologyDatabase
from engine.nlp.historical_attestation_verifier import HistoricalAttestationVerifier
from engine.nlp.hypothesis_validation_protocol import HypothesisValidationProtocol
from engine.nlp.neologism_detector import NeologismDetector
from engine.utils.phonotactics import initial_consonant_violation

logger = get_logger(__name__)


class IterativeHypothesisEngine:
    def __init__(self) -> None:
        self.donor_db = DeepDonorEtymologyDatabase()
        self.neologism_detector = NeologismDetector()
        self.attestation_verifier = HistoricalAttestationVerifier()
        self.validator_protocol = HypothesisValidationProtocol()
        self.reconstructor = ComparativeReconstructor()

    def prove_etymological_hypothesis(
        self,
        word: str,
        initial_finding: dict[str, Any],
        turkic_entries: list[dict[str, Any]] | None = None,
        fetcher_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        w = (word or "").strip().lower()
        entries = turkic_entries if turkic_entries is not None else initial_finding.get("turkic_languages", [])
        root = initial_finding.get("root", {}) or {}

        neologism = self.neologism_detector.detect(w)
        donor_match = self.donor_db.lookup(w)
        attestation = self.attestation_verifier.verify_attestation(w, entries, fetcher_results)
        reconstruction = self.reconstructor.reconstruct(w, entries)

        hypothesis = self._select_hypothesis(w, root, neologism, donor_match, reconstruction)

        if hypothesis is None:
            return {
                "word": w,
                "hypothesis_available": False,
                "proven_hypothesis": None,
                "attestation": attestation,
                "validation_report": None,
                "reason": (
                    "Ne donör sözlük eşleşmesi, ne modern türetme kalıbı, ne de yeterli "
                    "akraba tanığı bulundu. Hipotez ÜRETİLMEDİ (uydurma yapılmaz)."
                ),
            }

        val_report = self.validator_protocol.validate_hypothesis(w, hypothesis, attestation, entries)
        hypothesis["validation_report"] = val_report
        hypothesis["confidence_score"] = val_report["final_confidence_score"]

        return {
            "word": w,
            "hypothesis_available": True,
            "proven_hypothesis": hypothesis,
            "attestation": attestation,
            "validation_report": val_report,
        }

    @staticmethod
    def _select_hypothesis(
        w: str,
        root: dict[str, Any],
        neologism: dict[str, Any] | None,
        donor_match: dict[str, Any] | None,
        reconstruction: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Kanıt gücüne göre en iyi hipotezi seçer. Kanıt yoksa ``None``."""
        modern_meaning = root.get("meaning", "") or ""

        # 1. Donör sözlük eşleşmesi — en güçlü doğrudan kanıt
        if donor_match:
            return {
                "hypothesis_type": "Doğrulanmış alıntı kökeni",
                "donor_language": donor_match["donor_language"],
                "origin_form": donor_match["origin_form"],
                "proof_summary": donor_match.get("etymology", ""),
                "historical_meaning": donor_match.get("historical_meaning", ""),
                "modern_meaning": modern_meaning,
                "evidence_kind": "donor_lexicon",
            }

        # 2. Modern türetme (bileşik veya güçlü özleştirme eki)
        if neologism and neologism.get("is_neologism"):
            return {
                "hypothesis_type": "Modern Türkçe türetme (Cumhuriyet dönemi)",
                "donor_language": "Türkçe (modern türetme)",
                "origin_form": "+".join(neologism.get("components", [])) or w,
                "proof_summary": neologism.get("etymology_details", ""),
                "historical_meaning": "",
                "modern_meaning": modern_meaning,
                "evidence_kind": "morphological_derivation",
                "is_modern_derivation": True,
            }

        # 3. Karşılaştırmalı yöntemle ata biçim (en az 2 bağımsız dil tanığı)
        if reconstruction.get("evidence_available") and reconstruction.get("reconstructed_root"):
            return {
                "hypothesis_type": "Asli Proto-Türkçe kök (karşılaştırmalı yöntem)",
                "donor_language": "Proto-Türkçe",
                "origin_form": reconstruction["reconstructed_root"],
                "proof_summary": reconstruction.get("reconstruction_notes", ""),
                "historical_meaning": modern_meaning,
                "modern_meaning": modern_meaning,
                "evidence_kind": "comparative_method",
                "witness_count": reconstruction.get("witness_count", 0),
                "branches": reconstruction.get("branches", []),
                "applied_correspondences": reconstruction.get("applied_correspondences", []),
            }

        # 4. Fonotaktik ihlal — alıntı adayı, kaynak dil belirsiz
        violated, reason = initial_consonant_violation(w)
        if violated:
            return {
                "hypothesis_type": "Alıntı adayı (kaynak dil belirlenemedi)",
                "donor_language": "",
                "origin_form": w,
                "proof_summary": f"{reason}. Kaynak dil için donör sözlük kanıtı gerekiyor.",
                "historical_meaning": "",
                "modern_meaning": modern_meaning,
                "evidence_kind": "phonotactic_only",
                "is_loan_candidate": True,
            }

        return None
