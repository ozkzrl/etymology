"""
Etimoloji Hipotezi Doğrulama Protokolü (A-HVP)

Bir etimolojik hipotezi dört bağımsız aşamadan geçirir ve **yalnızca gerçekten
kanıt üretebilen aşamalardan** bir güven skoru hesaplar.

Temel ilke: KANIT YOKSA PUAN DA YOK
------------------------------------
Önceki sürümde dört aşamanın dördü de kanıt yokluğunda cömert varsayılan
puanlar veriyordu:

===========================  ==========================================
Aşama (ağırlık)              Kanıt yokken verilen puan
===========================  ==========================================
1 · Fonetik (%35)            karakter kümesi kesişimiyle 0.75'e kadar
2 · Kronoloji (%30)          tarih ayrıştırılamazsa **1.0**
3 · Semantik (%15)           veri eksikse **0.85**
4 · Triangulation (%20)      daima **0.95**
===========================  ==========================================

Sonuç: uydurma ``zzzqx`` kelimesi boş kanıtla **%96 "🟢 VALIDATED"** alıyordu.

Artık her aşama ``evidence_available`` bildirir. Kanıt üretemeyen aşamanın
ağırlığı toplamdan DÜŞÜLÜR, skor katkıda bulunan aşamalara normalize edilir ve
``evidence_coverage`` alanı kaç aşamanın gerçekten konuştuğunu raporlar.
Kapsam ``MIN_EVIDENCE_COVERAGE`` altındaysa rozet en fazla
``⚪ INSUFFICIENT_EVIDENCE`` olabilir.
"""
from __future__ import annotations

from typing import Any

from engine.config import A_HVP_WEIGHTS, BADGE_THRESHOLDS, MIN_EVIDENCE_COVERAGE
from engine.fetchers.base import TURKIC_LANGUAGE_COUNT, TURKIC_LANGUAGES_MAP
from engine.logging_setup import get_logger
from engine.nlp.cldf_lingpy_aligner import CldfLingPyAligner
from engine.nlp.diachronic_semantic_engine import DiachronicSemanticEngine
from engine.nlp.historical_attestation_verifier import HistoricalAttestationVerifier
from engine.utils.phonetic_rules import verify_phonetic_chain

logger = get_logger(__name__)


class PhoneticChainVerifier:
    """Aşama 1 — Ata biçim ile modern biçim arasında geçerli ses evrimi var mı?"""

    def __init__(self, aligner: CldfLingPyAligner | None = None):
        self.lingpy_aligner = aligner or CldfLingPyAligner()

    def verify(self, origin_form: str, word: str) -> dict[str, Any]:
        clean_origin = (origin_form or "").strip().lstrip("*")
        target = (word or "").strip()

        if not clean_origin or not target:
            return {
                "evidence_available": False,
                "is_valid": None,
                "score": None,
                "violations": [],
                "matched_rules": [],
                "reason": "Karşılaştırılacak ata biçim veya modern biçim yok.",
            }

        base = verify_phonetic_chain(clean_origin, target)
        if not base.get("evidence_available"):
            return {
                "evidence_available": False,
                "is_valid": None,
                "score": None,
                "violations": base.get("violations", []),
                "matched_rules": base.get("matched_rules", []),
                "reason": base.get("reason", "Fonetik zincir değerlendirilemedi."),
            }

        align = self.lingpy_aligner.align_sequences(clean_origin, target)
        alignment_similarity = float(align.get("phonetic_similarity") or 0.0)

        # Sıralı dizi benzerliği (%60) + ses sınıfı hizalaması (%40)
        combined = round(base["score"] * 0.6 + alignment_similarity * 0.4, 3)

        return {
            "evidence_available": True,
            "is_valid": bool(base["is_valid"]),
            "score": combined,
            "sequence_similarity": base.get("similarity"),
            "alignment_similarity": alignment_similarity,
            "violations": base.get("violations", []),
            "matched_rules": base.get("matched_rules", []),
            "alignment_details": {
                "aligned_seq1": align.get("aligned_seq1"),
                "aligned_seq2": align.get("aligned_seq2"),
                "sound_class_seq1": align.get("sound_class_seq1"),
                "sound_class_seq2": align.get("sound_class_seq2"),
            },
        }


class ChronologicalTimeLock:
    """
    Aşama 2 — Anakronizm kilidi.

    Kaynak dilin temas dönemi, kelimenin ilk tanıklanma tarihinden SONRA
    olamaz. Tarih bilinmiyorsa aşama kanıt üretmez (eskiden 1.0 veriyordu).
    """

    #: Donör dillerin Türkçe ile temas dönemi (yaklaşık, yıl olarak).
    DONOR_CONTACT_PERIODS: dict[str, int] = {
        "proto-türkçe": -500, "eski türkçe": 700, "çince": 200, "soğdca": 400,
        "sanskritçe": 500, "moğolca": 1200, "arapça": 900, "farsça": 900,
        "grekçe": 1000, "yunanca": 1000, "ermenice": 1000, "rumca": 1300,
        "slavca": 1300, "rusça": 1700, "italyanca": 1300, "venedikçe": 1300,
        "macarca": 1400, "fransızca": 1800, "ingilizce": 1900, "almanca": 1850,
        "latince": 1500,
    }

    def __init__(self) -> None:
        self._verifier = HistoricalAttestationVerifier()

    def parse_year_or_century(self, text: str) -> int | None:
        """Serbest metinden yıl çıkarır; sayfa/cilt numaralarını dışlar."""
        if not text:
            return None
        year = self._verifier.parse_year(text)
        if year is not None:
            return year

        import re

        lowered = text.lower()
        masked = re.sub(r"\b(?:s|sf|sayfa|p|pp|cilt|c|nr|no|vol)\.?\s*\d+", " ", lowered)
        m = re.search(r"(\d{1,2})\.?\s*(?:yy|yüzyıl|century)", masked)
        if m:
            century = int(m.group(1))
            approx = (century - 1) * 100 + 50
            return -approx if ("m.ö" in lowered or "mö " in lowered or "bc" in lowered) else approx
        return None

    def donor_contact_year(self, donor_language: str) -> int | None:
        d = (donor_language or "").strip().lower()
        for name, year in self.DONOR_CONTACT_PERIODS.items():
            if name in d:
                return year
        return None

    def verify(self, donor_language: str, attestation: dict[str, Any] | None) -> dict[str, Any]:
        """
        :param donor_language: Hipotezin öne sürdüğü kaynak dil.
        :param attestation: :class:`HistoricalAttestationVerifier` çıktısı.
            Serbest ``proof_summary`` metni ARTIK GİRDİ DEĞİLDİR; eski sürümde
            oradaki sayfa numaraları yıl sanılıyordu.
        """
        t_source = self.donor_contact_year(donor_language)
        t_target = (attestation or {}).get("first_attestation_year")

        if t_source is None or t_target is None:
            missing = []
            if t_source is None:
                missing.append(f"donör dil temas dönemi bilinmiyor ({donor_language or '—'})")
            if t_target is None:
                missing.append("kelimenin tarihli ilk tanıklaması yok")
            return {
                "evidence_available": False,
                "is_valid": None,
                "score": None,
                "source_year": t_source,
                "attestation_year": t_target,
                "reason": "Kronoloji değerlendirilemedi: " + ", ".join(missing),
            }

        if t_source > t_target:
            return {
                "evidence_available": True,
                "is_valid": False,
                "score": 0.0,
                "source_year": t_source,
                "attestation_year": t_target,
                "violation": (
                    f"ANAKRONİZM: Kaynak dil teması (~{t_source}) kelimenin ilk "
                    f"tanıklamasından ({t_target}) sonradır."
                ),
            }

        # Temas ile tanıklama arasındaki mesafe ne kadar makulse skor o kadar yüksek
        gap = t_target - t_source
        score = 1.0 if gap <= 800 else max(0.5, 1.0 - (gap - 800) / 4000)
        return {
            "evidence_available": True,
            "is_valid": True,
            "score": round(score, 3),
            "source_year": t_source,
            "attestation_year": t_target,
            "reason": f"Kronolojik sıra tutarlı (temas ~{t_source}, tanıklama {t_target}).",
        }


class SemanticDriftEvaluator:
    """Aşama 3 — Tarihsel anlam ile modern anlam arasındaki mesafe makul mü?"""

    def __init__(self, engine: DiachronicSemanticEngine | None = None):
        self.engine = engine or DiachronicSemanticEngine()

    def verify(self, historical_meaning: str, modern_meaning: str) -> dict[str, Any]:
        res = self.engine.evaluate_diachronic_trajectory(historical_meaning, modern_meaning)
        if not res.get("evidence_available"):
            return {
                "evidence_available": False,
                "is_valid": None,
                "score": None,
                "reason": res.get("reason"),
                "trajectory_details": res,
            }
        distance = res["total_shift_distance"]
        return {
            "evidence_available": True,
            "is_valid": bool(res["is_plausible"]),
            "score": round(max(0.0, 1.0 - distance), 3),
            "reason": res.get("reason"),
            "trajectory_details": res,
        }


class CrossCognateTriangulator:
    """
    Aşama 4 — Kelimenin GERÇEK akraba dağılımı.

    Eski sürüm ``generate_turkic_cognate_candidates(word)`` çağırıp KENDİ
    ÜRETTİĞİ varyantları sayıyordu; transkripsiyon nedeniyle sayı her zaman
    1'den büyük çıkıyor ve skor **daima 0.95** oluyordu. Artık yalnızca veri
    katmanından gelen gerçek kayıtlar sayılır.
    """

    def verify(self, word: str, turkic_entries: list[dict[str, Any]] | None) -> dict[str, Any]:
        entries = turkic_entries or []
        real_langs = {
            e.get("lang_code") for e in entries if e.get("lang_code") in TURKIC_LANGUAGES_MAP
        }
        # Bağımsız kaynak çeşitliliği: tek bir kaynağın ürettiği liste zayıf kanıttır.
        sources = {e.get("source") for e in entries if e.get("source")}
        live_sources = {
            e.get("source") for e in entries
            if e.get("source") and e.get("origin") == "live"
        }

        if not real_langs:
            return {
                "evidence_available": False,
                "is_valid": None,
                "score": None,
                "cognate_count": 0,
                "languages": [],
                "reason": "Veri katmanında hiç Türki dil karşılığı bulunamadı.",
            }

        spread = len(real_langs) / TURKIC_LANGUAGE_COUNT
        source_factor = min(1.0, len(sources) / 3.0)
        live_factor = min(1.0, len(live_sources) / 2.0) if live_sources else 0.4

        score = round(0.55 * min(1.0, spread / 0.4) + 0.25 * source_factor + 0.20 * live_factor, 3)

        return {
            "evidence_available": True,
            "is_valid": True,
            "score": min(1.0, score),
            "cognate_count": len(real_langs),
            "languages": sorted(real_langs),
            "spreading_ratio": round(spread, 3),
            "source_count": len(sources),
            "live_source_count": len(live_sources),
            "sample_cognates": [e.get("word") for e in entries[:6] if e.get("word")],
        }


class HypothesisValidationProtocol:
    """Dört aşamalı hakem protokolü ve kanıt kapsamına göre normalize skor."""

    def __init__(self) -> None:
        self.phonetic_verifier = PhoneticChainVerifier()
        self.time_lock = ChronologicalTimeLock()
        self.semantic_evaluator = SemanticDriftEvaluator()
        self.cognate_triangulator = CrossCognateTriangulator()

    def validate_hypothesis(
        self,
        word: str,
        hypothesis: dict[str, Any],
        attestation_record: dict[str, Any] | None = None,
        turkic_entries: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raw_origin = hypothesis.get("origin_form") or word
        clean_origin = str(raw_origin).strip().lstrip("*") or word
        donor_lang = hypothesis.get("donor_language", "")
        origin_form = f"*{clean_origin}" if donor_lang == "Proto-Türkçe" else clean_origin

        phonetic_res = self.phonetic_verifier.verify(origin_form, word)
        time_res = self.time_lock.verify(donor_lang, attestation_record)
        semantic_res = self.semantic_evaluator.verify(
            hypothesis.get("historical_meaning", ""), hypothesis.get("modern_meaning", "")
        )
        cognate_res = self.cognate_triangulator.verify(word, turkic_entries)

        stages = {
            "phonetic": phonetic_res,
            "chronology": time_res,
            "semantic": semantic_res,
            "triangulation": cognate_res,
        }

        # --- Kanıt kapsamına göre normalize skor ---
        contributing_weight = 0.0
        weighted_sum = 0.0
        for key, res in stages.items():
            if not res.get("evidence_available") or res.get("score") is None:
                continue
            weight = A_HVP_WEIGHTS[key]
            contributing_weight += weight
            weighted_sum += weight * float(res["score"])

        total_weight = sum(A_HVP_WEIGHTS.values())
        evidence_coverage = round(contributing_weight / total_weight, 3) if total_weight else 0.0
        # `stage_score`: ÖLÇÜLEBİLEN kanıtın kalitesi.
        # `total_score` : kapsamla ağırlıklandırılmış yayımlanan güven.
        # İkisi ayrı tutulur; aksi hâlde "kanıt eksik" ile "kanıt kötü" aynı
        # kefeye girer ve iyi belgelenmiş bir etimoloji, yalnızca tarih verisi
        # eksik olduğu için reddedilir.
        stage_score = round(weighted_sum / contributing_weight, 3) if contributing_weight else 0.0
        total_score = round(stage_score * evidence_coverage, 3)

        rejections: list[str] = []
        for res in stages.values():
            rejections.extend(res.get("violations", []) or [])
            if res.get("violation"):
                rejections.append(res["violation"])

        if any(s.get("is_valid") is False for s in stages.values()):
            stage_score = round(stage_score * 0.4, 3)
            total_score = round(total_score * 0.4, 3)
        if time_res.get("is_valid") is False:
            stage_score = min(stage_score, 0.30)
            total_score = min(total_score, 0.30)

        status_code, badge = self._decide(stage_score, evidence_coverage, rejections)

        report = {
            "status_code": status_code,
            "badge": badge,
            "final_confidence_score": total_score,
            "score_percentage": f"%{round(total_score * 100, 1)}",
            "stage_score": stage_score,
            "evidence_coverage": evidence_coverage,
            "contributing_stages": sorted(
                k for k, v in stages.items() if v.get("evidence_available") and v.get("score") is not None
            ),
            "missing_evidence": sorted(
                k for k, v in stages.items() if not v.get("evidence_available") or v.get("score") is None
            ),
            "stage_breakdown": {
                "stage1_phonetic_chain": phonetic_res,
                "stage2_time_lock": time_res,
                "stage3_semantic_drift": semantic_res,
                "stage4_cognate_triangulation": cognate_res,
            },
            "rejection_reasons": rejections,
            "weights": dict(A_HVP_WEIGHTS),
        }
        logger.debug(
            "A-HVP %r: skor=%.3f kapsam=%.2f rozet=%s", word, total_score, evidence_coverage, status_code
        )
        return report

    @staticmethod
    def _decide(stage_score: float, coverage: float, rejections: list[str]) -> tuple[str, str]:
        """
        Rozet kararı.

        Karar ``stage_score`` (ölçülebilen kanıtın KALİTESİ) üzerinden verilir;
        ``coverage`` ise bir KAPI görevi görür. Böylece:

        * kanıtın yarısından azı ölçülebildiyse -> YETERSİZ KANIT
        * ölçülebilen kanıt bir ihlal gösteriyorsa -> REDDEDİLDİ
        * ölçülebilen kanıt iyi ama eksikse -> DOĞRULANDI (kısmi kanıt)
        """
        if coverage < MIN_EVIDENCE_COVERAGE:
            return (
                "INSUFFICIENT_EVIDENCE",
                f"⚪ YETERSİZ KANIT (aşamaların yalnızca %{coverage * 100:.0f}'i değerlendirilebildi)",
            )
        if rejections:
            return "REJECTED", "🔴 REDDEDİLDİ (anakronizm veya fonetik zincir ihlali)"

        partial = coverage < 0.999
        if stage_score >= BADGE_THRESHOLDS["validated"]:
            suffix = f" — kısmi kanıt, %{coverage * 100:.0f} kapsam" if partial else ""
            return "VALIDATED", f"🟢 DOĞRULANDI (kanıta dayalı){suffix}"
        if stage_score >= BADGE_THRESHOLDS["needs_review"]:
            suffix = f" (%{coverage * 100:.0f} kapsam)" if partial else ""
            return "NEEDS_REVIEW", f"🟡 İNCELEME GEREKLİ{suffix}"
        return "REJECTED", "🔴 REDDEDİLDİ (ölçülebilen kanıt zayıf)"
