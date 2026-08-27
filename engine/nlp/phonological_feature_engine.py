"""
Artikülatör Fonetik Özellik Motoru (Articulatory Feature Engine)

Sesleri artikülatör özellik vektörlerine çevirir ve ses/dizi mesafelerini
hesaplar. Vektörler **gerçek PanPhon** kütüphanesinden gelir.

Neden değişti
-------------
Önceki sürüm dosya başlığında "PanPhon Articulatory Feature Engine" yazmasına
rağmen ``panphon`` kütüphanesini kullanmıyordu; **elle girilmiş 35 karakter ×
21 özellik = 735 sayıdan** oluşan, hiçbir kaynağa referans vermeyen ve
doğrulanamaz bir matris taşıyordu. Üstelik matrisin anahtarları IPA değil
**Türk Latin harfleriydi**.

Gerçek PanPhon **6.367 IPA segmenti** ve 24 artikülatör özellik içerir.
Türkçe imla önce Epitran ile IPA'ya çevrilir.

Kurulum: ``pip install -e ".[phon]"``. Kütüphane yoksa motor, azaltılmış ama
dürüst bir yedek moda düşer ve bunu ``backend`` alanında bildirir.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from engine.logging_setup import get_logger
from engine.utils.orthography import to_comparison_form

logger = get_logger(__name__)

#: Türkçe Latin harfi -> IPA. Epitran yoksa bu tablo kullanılır.
FALLBACK_IPA_MAP: dict[str, str] = {
    "a": "a", "e": "e", "ı": "ɯ", "i": "i", "o": "o", "ö": "ø", "u": "u", "ü": "y",
    "b": "b", "c": "d͡ʒ", "ç": "t͡ʃ", "d": "d", "f": "f", "g": "ɡ", "ğ": "ɰ",
    "h": "h", "j": "ʒ", "k": "k", "l": "l", "m": "m", "n": "n", "p": "p",
    "r": "ɾ", "s": "s", "ş": "ʃ", "t": "t", "v": "v", "y": "j", "z": "z",
    "ŋ": "ŋ", "ŕ": "r", "ĺ": "ʎ", "q": "q", "w": "w", "x": "x",
}

#: PanPhon Hamming özellik mesafesini [0,1] aralığına yaymak için bölen.
#: Akraba çiftler tipik olarak 0.01-0.10, alâkasız çiftler 0.25+ değer alır;
#: 0.30 bölen ikisini net ayırır.
DISTANCE_SCALE = 0.30

#: Kısa kelimelerde tek bir ekleme/silmenin skoru çökertmesini engelleyen taban uzunluk.
MIN_EFFECTIVE_LENGTH = 4

_FEATURE_TABLE = None
_DISTANCE = None
_EPITRAN = None
_BACKEND: str | None = None


def _load_backend() -> str:
    """PanPhon/Epitran yüklemeyi dener; kullanılan arka ucu döndürür."""
    global _FEATURE_TABLE, _DISTANCE, _EPITRAN, _BACKEND
    if _BACKEND is not None:
        return _BACKEND

    try:
        import panphon
        import panphon.distance

        _FEATURE_TABLE = panphon.FeatureTable()
        _DISTANCE = panphon.distance.Distance()
        _BACKEND = "panphon"
        logger.info("PanPhon yüklendi: %d IPA segmenti", len(_FEATURE_TABLE.segments))
    except Exception:
        logger.info(
            'panphon kurulu değil; azaltılmış fonetik moda düşülüyor. '
            'Kurulum: pip install -e ".[phon]"'
        )
        _BACKEND = "fallback"
        return _BACKEND

    try:
        import epitran

        _EPITRAN = epitran.Epitran("tur-Latn")
        logger.info("Epitran yüklendi: tur-Latn")
    except Exception:
        logger.info("epitran kurulu değil; IPA çevirisi yedek tabloyla yapılacak")
        _EPITRAN = None
    return _BACKEND


def backend_name() -> str:
    """Kullanılan fonetik arka uç: ``panphon`` veya ``fallback``."""
    return _load_backend()


@lru_cache(maxsize=4096)
def to_ipa(text: str) -> str:
    """Türkçe imlayı IPA'ya çevirir."""
    _load_backend()
    t = (text or "").strip().lower().lstrip("*")
    if not t:
        return ""
    if _EPITRAN is not None:
        try:
            return _EPITRAN.transliterate(t)
        except Exception:
            logger.warning("Epitran çevirisi başarısız: %r", t, exc_info=True)
    return "".join(FALLBACK_IPA_MAP.get(ch, ch) for ch in t)


class PhonologicalFeatureEngine:
    """PanPhon tabanlı artikülatör özellik ve mesafe motoru."""

    @property
    def backend(self) -> str:
        return backend_name()

    @lru_cache(maxsize=2048)  # noqa: B019  (örnek başına değil, sınıf düzeyinde önbellek yeterli)
    def _vector(self, segment: str) -> tuple[int, ...]:
        _load_backend()
        if _FEATURE_TABLE is not None:
            try:
                vecs = _FEATURE_TABLE.word_to_vector_list(segment, numeric=True)
                if vecs:
                    return tuple(vecs[0])
            except Exception:
                logger.debug("PanPhon vektörü alınamadı: %r", segment)
        return ()

    def get_feature_vector(self, char: str) -> list[int]:
        """Tek bir sesin artikülatör özellik vektörü (PanPhon: 24 boyut)."""
        return list(self._vector(to_ipa(char) or char))

    def articulatory_distance(self, char1: str, char2: str) -> float:
        """
        İki ses arasındaki normalize artikülatör mesafe (0.0 aynı, 1.0 zıt).

        PanPhon varsa özellik vektörleri üzerinden Hamming mesafesi;
        yoksa basit eşitlik karşılaştırması.
        """
        if char1 == char2:
            return 0.0
        v1, v2 = self._vector(to_ipa(char1) or char1), self._vector(to_ipa(char2) or char2)
        if not v1 or not v2 or len(v1) != len(v2):
            return 1.0 if char1 != char2 else 0.0
        diff = sum(1 for a, b in zip(v1, v2, strict=False) if a != b)
        return round(diff / len(v1), 3)

    # Geriye dönük uyumluluk
    articulatory_hamming_distance = articulatory_distance

    def _fallback_distance(self, s1: str, s2: str) -> tuple[float, float]:
        """PanPhon yokken artikülatör ağırlıklı düzenleme mesafesi."""
        m, n = len(s1), len(s2)
        dp = [[0.0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = float(i)
        for j in range(n + 1):
            dp[0][j] = float(j)
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                # Ayrı iki ses hiçbir zaman "neredeyse bedava" olmamalı:
                # taban 0.35 + özellik farkı.
                raw = self.articulatory_distance(s1[i - 1], s2[j - 1])
                cost = 0.0 if raw == 0.0 else 0.35 + 0.65 * raw
                dp[i][j] = min(dp[i - 1][j] + 1.0, dp[i][j - 1] + 1.0, dp[i - 1][j - 1] + cost)
        dist = dp[m][n]
        return round(dist, 3), round(dist / float(max(m, n, 1)), 3)

    def sequence_phonological_distance(self, seq1: str, seq2: str) -> dict[str, Any]:
        """
        İki biçim arasındaki artikülatör ağırlıklı düzenleme mesafesi.

        Dönüş anahtarları TEK ŞEMADIR. Eski sürümde boş girdi dalı
        ``{distance, similarity, matrix}``, normal dal ise
        ``{phonological_edit_distance, normalized_articulatory_distance,
        phonetic_similarity}`` döndürüyordu; çağıranlar sessizce
        varsayılanlara düşüyordu.
        """
        s1 = to_comparison_form(seq1 or "")
        s2 = to_comparison_form(seq2 or "")

        if not s1 or not s2:
            return {
                "seq1": s1,
                "seq2": s2,
                "backend": self.backend,
                "evidence_available": False,
                "phonological_edit_distance": None,
                "normalized_articulatory_distance": None,
                "phonetic_similarity": None,
            }

        ipa1, ipa2 = to_ipa(s1), to_ipa(s2)
        _load_backend()

        if _DISTANCE is not None:
            # PanPhon'un Hamming tabanlı özellik düzenleme mesafesi (uzunluğa
            # normalize). Ham değer aralığı dar olduğu için (akraba çiftler
            # ~0.01-0.10, alâkasız çiftler ~0.25+) DISTANCE_SCALE ile
            # [0,1] aralığına yayılır.
            try:
                dist = float(_DISTANCE.hamming_feature_edit_distance(ipa1, ipa2))
                # Uzunluk tabanı: 2-3 sesli kelimelerde tek bir ekleme/silme
                # oransal olarak felaket görünür (su ~ sub gibi düzenli bir
                # ses düşmesi %0 benzerlik alırdı). Taban uzunluk 4 alınır.
                effective_len = max(len(ipa1), len(ipa2), MIN_EFFECTIVE_LENGTH)
                norm = round(min(1.0, (dist / effective_len) / DISTANCE_SCALE), 3)
                dist = round(dist, 3)
            except Exception:
                logger.warning("PanPhon mesafesi hesaplanamadı: %r ~ %r", ipa1, ipa2, exc_info=True)
                dist, norm = self._fallback_distance(s1, s2)
        else:
            dist, norm = self._fallback_distance(s1, s2)
        norm = min(1.0, max(0.0, norm))
        return {
            "seq1": s1,
            "seq2": s2,
            "ipa1": ipa1,
            "ipa2": ipa2,
            "backend": self.backend,
            "evidence_available": True,
            "phonological_edit_distance": round(dist, 3),
            "normalized_articulatory_distance": norm,
            "phonetic_similarity": round(max(0.0, 1.0 - norm), 3),
        }
