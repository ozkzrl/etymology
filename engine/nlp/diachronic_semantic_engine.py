"""
Diyakronik Semantik Vektör Analizi (Diachronic Semantic Shift Engine)

Tarihsel anlam ile modern anlam arasındaki semantik mesafeyi ölçer ve
etimolojik olarak imkânsız anlam sıçramalarını işaretler.

Yeniden üretilebilirlik notu
----------------------------
Bu modül daha önce Python'un yerleşik ``hash()`` fonksiyonunu kullanıyordu.
CPython'da string hash'i süreç başına rastgele tohumlanır (``PYTHONHASHSEED``);
bu yüzden aynı kelime her çalıştırmada FARKLI bir vektör, farklı bir mesafe ve
farklı bir A-HVP rozeti üretiyordu. Artık ``hashlib.blake2b`` kullanılır ve
çıktı deterministiktir.

Sentence-Transformers opsiyoneldir (``pip install -e ".[semantic]"``). Kurulu
değilse modül sessizce zayıf bir karakter n-gram temsiline düşmez; semantik
aşamanın kanıt üretemediğini açıkça bildirir (``evidence_available: False``)
ve A-HVP bu aşamanın ağırlığını toplamdan düşer.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any

from engine.logging_setup import get_logger

logger = get_logger(__name__)

_ST_MODEL = None
_ST_TRIED = False
_ST_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L6-v2"


def get_sentence_transformer():
    """Modeli tembel (lazy) yükler. Import anında ağ/disk erişimi yapılmaz."""
    global _ST_MODEL, _ST_TRIED
    if _ST_TRIED:
        return _ST_MODEL
    _ST_TRIED = True
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.info(
            "sentence-transformers kurulu değil; semantik aşama kanıt üretmeyecek. "
            "Etkinleştirmek için: pip install -e \".[semantic]\""
        )
        return None
    try:
        _ST_MODEL = SentenceTransformer(_ST_MODEL_NAME)
        logger.info("Semantik model yüklendi: %s", _ST_MODEL_NAME)
    except Exception:
        logger.warning("Semantik model yüklenemedi: %s", _ST_MODEL_NAME, exc_info=True)
        _ST_MODEL = None
    return _ST_MODEL


def has_semantic_model() -> bool:
    return get_sentence_transformer() is not None


class DenseSemanticVectorizer:
    """Metni sabit boyutlu bir yoğun vektöre indirger."""

    def __init__(self, vocab_size: int = 64):
        self.vocab_size = vocab_size

    def extract_ngrams(self, text: str, n_range: tuple[int, int] = (2, 4)) -> list[str]:
        t = re.sub(r"[^\w\s]", "", (text or "").lower())
        ngrams: list[str] = []
        for token in t.split():
            ngrams.append(token)
            for n in range(n_range[0], n_range[1] + 1):
                for i in range(len(token) - n + 1):
                    ngrams.append(token[i : i + n])
        return ngrams

    @staticmethod
    def _stable_bucket(gram: str, buckets: int) -> int:
        """Süreçler arası sabit hash. ``hash()`` tohumlanmış olduğu için kullanılmaz."""
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % buckets

    def vectorise(self, text: str) -> tuple[list[float], bool]:
        """
        (vektör, transformer_kullanıldı) döndürür.

        İkinci değer ``False`` ise vektör yalnızca ortografik (karakter n-gram)
        bir temsildir; semantik kanıt sayılmaz.
        """
        model = get_sentence_transformer()
        if model is not None:
            try:
                emb = model.encode(text or "", convert_to_numpy=True)
                norm = math.sqrt(sum(float(x) * float(x) for x in emb)) or 1.0
                return [round(float(x) / norm, 4) for x in emb[:64]], True
            except Exception:
                logger.warning("Semantik kodlama başarısız, ortografik temsile düşülüyor", exc_info=True)

        ngrams = self.extract_ngrams(text)
        if not ngrams:
            return [0.0] * self.vocab_size, False

        counts = Counter(ngrams)
        vec = [0.0] * self.vocab_size
        for gram, freq in counts.items():
            vec[self._stable_bucket(gram, self.vocab_size)] += 1.0 + math.log(freq)

        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [round(x / norm, 4) for x in vec], False


class DiachronicSemanticEngine:
    """Tarihsel ve modern anlam arasındaki semantik mesafeyi değerlendirir."""

    # Bu eşiğin üzerindeki mesafe, anlamların birbirinden kopuk olduğunu gösterir.
    THETA_THRESHOLD = 0.85

    def __init__(self, vocab_size: int = 64):
        self.vectorizer = DenseSemanticVectorizer(vocab_size=vocab_size)

    def cosine_distance(self, v1: list[float], v2: list[float]) -> float:
        """İki birim vektör arasındaki kosinüs mesafesi (0.0 aynı, 1.0 dik)."""
        dot = sum(a * b for a, b in zip(v1, v2, strict=False))
        return round(1.0 - max(0.0, min(1.0, dot)), 4)

    def evaluate_diachronic_trajectory(
        self,
        origin_meaning: str,
        modern_meaning: str,
        timeline: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Tarihsel anlam ile modern anlam arasındaki semantik mesafeyi ölçer.

        ``evidence_available`` alanı, bu değerlendirmenin A-HVP skoruna
        katkıda bulunup bulunamayacağını belirler. Veri eksikse veya yalnızca
        ortografik temsil kullanılabildiyse ``False`` döner ve aşama
        ağırlığı toplam skordan düşülür — eskiden bu durumda otomatik 0.85
        veriliyordu.

        :param timeline: Tarihsel katman etiketleri. Şu an yalnızca çıktıda
            raporlanır; çok noktalı yörünge hesabı için ayrılmıştır.
        """
        s_m = (origin_meaning or "").strip()
        m_m = (modern_meaning or "").strip()
        layers = list(timeline or [])

        if not s_m or not m_m:
            return {
                "origin_meaning": s_m,
                "modern_meaning": m_m,
                "total_shift_distance": None,
                "theta_threshold": self.THETA_THRESHOLD,
                "is_plausible": None,
                "evidence_available": False,
                "trajectory_status": "Kanıt Yok",
                "reason": "Tarihsel veya modern anlam verisi yok; semantik aşama değerlendirilemedi.",
                "transformer_active": False,
                "timeline_layers": layers,
            }

        v_start, used_model_a = self.vectorizer.vectorise(s_m)
        v_end, used_model_b = self.vectorizer.vectorise(m_m)
        transformer_active = used_model_a and used_model_b

        distance = self.cosine_distance(v_start, v_end)

        if not transformer_active:
            # Karakter n-gram temsili anlamı değil imlayı ölçer; kanıt sayılmaz.
            return {
                "origin_meaning": s_m,
                "modern_meaning": m_m,
                "total_shift_distance": distance,
                "theta_threshold": self.THETA_THRESHOLD,
                "is_plausible": None,
                "evidence_available": False,
                "trajectory_status": "Kanıt Yok (semantik model kurulu değil)",
                "reason": (
                    "sentence-transformers kurulu olmadığı için yalnızca ortografik benzerlik "
                    "hesaplanabildi; bu semantik kanıt sayılmaz. Etkinleştirmek için: "
                    'pip install -e ".[semantic]"'
                ),
                "transformer_active": False,
                "orthographic_distance": distance,
                "timeline_layers": layers,
            }

        is_plausible = distance <= self.THETA_THRESHOLD
        reason = "Tarihsel ve modern anlam semantik uzayda birbirine yakın; anlam kayması makul."
        if not is_plausible:
            reason = (
                f"SEMANTİK KOPUKLUK: Anlamlar arası mesafe ({distance}) "
                f"theta sınırını ({self.THETA_THRESHOLD}) aştı."
            )

        return {
            "origin_meaning": s_m,
            "modern_meaning": m_m,
            "semantic_vector_origin": v_start[:8],
            "semantic_vector_modern": v_end[:8],
            "total_shift_distance": distance,
            "theta_threshold": self.THETA_THRESHOLD,
            "is_plausible": is_plausible,
            "evidence_available": True,
            "trajectory_status": "Makul Anlam Kayması" if is_plausible else "Şüpheli Etimoloji (Semantik Sıçrama)",
            "reason": reason,
            "transformer_active": True,
            "timeline_layers": layers,
        }
