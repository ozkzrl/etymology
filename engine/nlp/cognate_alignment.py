"""
Çapraz Türki Lehçe Dağılım Skorlaması (Cross-Turkic Cognate Distribution)

Alıntı keşif hattının **Katman 2** uygulaması: bir kelimenin kaç Türki dilde
karşılığı bulunduğunu ölçer. Geniş yayılım asli
Öz Türkçe kök göstergesi, dar yayılım son dönem alıntı göstergesidir.

Düzeltilen sorunlar
-------------------
* Yayılım oranı koda gömülü ``25`` sabitine bölünüyordu; harita 18 dil
  içerdiği için oran matematiksel olarak %72'yi aşamıyordu. Artık
  ``TURKIC_LANGUAGE_COUNT`` kullanılır.
* Lehçe sayımı serbest metin ``lang_name`` alanı üzerinden yapılıyordu;
  "TDK Ağızları (Sinop)" ve "TDK Ağızları (Kastamonu)" iki ayrı dil sayılıyor,
  kitap/makale künyeleri de "lehçe" olarak yayılımı şişiriyordu. Artık yalnızca
  ``TURKIC_LANGUAGES_MAP``'te tanımlı ``lang_code`` değerleri sayılır.
* ``alignment_score`` daima ``85.0 + …`` idi; yani hiçbir hizalama yapılmadan
  her kelime 85–100 arası bir "hizalama skoru" alıyordu. Artık gerçek fonetik
  hizalamadan hesaplanır.
* Eşikler tasarım hedefindeki değerlerle (>%70 öz / <%20 alıntı) hizalandı.
"""
from __future__ import annotations

from typing import Any

from engine.fetchers.base import TURKIC_LANGUAGE_COUNT, TURKIC_LANGUAGES_MAP
from engine.logging_setup import get_logger

logger = get_logger(__name__)

#: Plan dokümanı: yayılım > %70 -> yüksek ihtimalle asli Öz Türkçe
NATIVE_SPREAD_THRESHOLD = 0.70
#: Plan dokümanı: yayılım < %20 -> yüksek ihtimalle son dönem alıntı
LOAN_SPREAD_THRESHOLD = 0.20


class CognateAlignmentEngine:
    def __init__(self, aligner: Any | None = None):
        # Gerçek hizalayıcı geç bağlanır (döngüsel import ve maliyet için).
        self._aligner = aligner

    @property
    def aligner(self) -> Any:
        if self._aligner is None:
            from engine.nlp.cldf_lingpy_aligner import CldfLingPyAligner

            self._aligner = CldfLingPyAligner()
        return self._aligner

    def evaluate_cognate_distribution(
        self, word: str, turkic_entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Kelimenin Türki diller haritasındaki yayılımını ve ortalama hizalama skorunu hesaplar."""
        w = word.strip().lower()

        # Yalnızca GERÇEK dil kayıtları sayılır. Kitap künyesi, makale başlığı
        # ve "donor"/"ai" gibi sözde kodlar yayılıma dâhil edilmez.
        real_langs = {
            e.get("lang_code")
            for e in (turkic_entries or [])
            if e.get("lang_code") in TURKIC_LANGUAGES_MAP
        }
        dialect_count = len(real_langs)

        if dialect_count == 0:
            return {
                "word": w,
                "spreading_ratio": 0.0,
                "present_dialects_count": 0,
                "present_languages": [],
                "total_language_count": TURKIC_LANGUAGE_COUNT,
                "alignment_score": None,
                "evidence_available": False,
                "assessment": "Veri katmanında Türki dil karşılığı bulunamadı",
            }

        spreading_ratio = round(dialect_count / TURKIC_LANGUAGE_COUNT, 3)

        if spreading_ratio >= NATIVE_SPREAD_THRESHOLD:
            assessment = "Yüksek çapraz-lehçe yayılımı (asli Proto-Türkçe kök göstergesi)"
        elif spreading_ratio >= LOAN_SPREAD_THRESHOLD:
            assessment = "Orta seviye bölgesel yayılım (Oğuz / Kıpçak / Karluk katmanı)"
        else:
            assessment = "Dar / lokal yayılım (ağız terimi veya son dönem alıntı göstergesi)"

        # Gerçek hizalama: sorgu kelimesi ile her lehçe biçimi arasındaki
        # fonetik benzerliğin ortalaması. Uydurma 85.0 tabanı kaldırıldı.
        similarities: list[float] = []
        for entry in turkic_entries or []:
            if entry.get("lang_code") not in TURKIC_LANGUAGES_MAP:
                continue
            other = (entry.get("word") or "").strip()
            if not other:
                continue
            try:
                res = self.aligner.align_sequences(w, other)
                sim = res.get("phonetic_similarity")
                if sim is not None:
                    similarities.append(float(sim))
            except Exception:
                logger.warning("Hizalama başarısız: %r ~ %r", w, other, exc_info=True)

        alignment_score = round(sum(similarities) / len(similarities), 3) if similarities else None

        return {
            "word": w,
            "spreading_ratio": spreading_ratio,
            "present_dialects_count": dialect_count,
            "present_languages": sorted(real_langs),
            "total_language_count": TURKIC_LANGUAGE_COUNT,
            "alignment_score": alignment_score,
            "aligned_pair_count": len(similarities),
            "evidence_available": True,
            "assessment": assessment,
        }
