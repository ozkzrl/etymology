"""
Tarihsel İlk Tanıklama Doğrulayıcı (Historical Attestation Verifier)

Bir kelimenin **gerçek** ilk yazılı tanıklamasını, veri katmanından gelen
kayıtlardan çıkarır.

Yeniden yazılma gerekçesi
-------------------------
Önceki uygulama, eşleşme bulamadığında şu cümleyi UYDURUYORDU::

    "'<kelime>' için ilk tanıklama 13.-19. yüzyıl Osmanlı/Çağatay metinleri
     veya Cumhuriyet dönemi özleştirme kayıtlarındadır."

Bu metin daha sonra A-HVP kronolojik zaman kilidine girdi olarak veriliyor,
oradaki yıl ayrıştırıcısı "19. yüzyıl" ifadesini yakalayıp 1850 yılını
üretiyordu. Yani **tamamen uydurulmuş bir tarih bilimsel skora dönüşüyordu**.

Artık kanıt yoksa ``verified: False`` ve ``record: None`` döner; A-HVP bu
durumda kronoloji aşamasının ağırlığını toplam skordan düşer.
"""
from __future__ import annotations

import re
from typing import Any

from engine.logging_setup import get_logger

logger = get_logger(__name__)

#: Bilinen tarihî kaynaklar ve kesin tarihleri.
#: Bunlar kelime değil KAYNAK bilgisidir; kelime bazlı hardcode değildir.
DATED_SOURCES: list[tuple[re.Pattern[str], int, str]] = [
    (re.compile(r"orhun|köktürk|kül\s*tigin|bilge\s*kağan", re.I), 735, "735 Orhun Yazıtları"),
    (re.compile(r"divan.?[uı]?\s*lugat|kaşgarl|dlt\b|divan-i lugat", re.I), 1074, "1074 Divânu Lugâti't-Türk (Kâşgarlı Mahmud)"),
    (re.compile(r"kutadgu\s*bilig", re.I), 1069, "1069 Kutadgu Bilig (Yusuf Has Hacib)"),
    (re.compile(r"codex\s*cumanicus", re.I), 1303, "1303 Codex Cumanicus"),
    (re.compile(r"atebet.?ül.?hakayık|atabet", re.I), 1150, "yak. 1150 Atebetü'l-Hakayık"),
    (re.compile(r"kamus-?ı\s*türkî|şemsettin\s*sami", re.I), 1901, "1901 Kamûs-ı Türkî (Şemseddin Sâmi)"),
    (re.compile(r"lehçe-?i\s*osman", re.I), 1876, "1876 Lehce-i Osmânî"),
    (re.compile(r"tarama\s*sözlü", re.I), 1300, "13.-19. yy TDK Tarama Sözlüğü"),
]

_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9]|[6-9][0-9]{2})\b")


class HistoricalAttestationVerifier:
    def verify_attestation(
        self,
        word: str,
        live_entries: list[dict[str, Any]] | None = None,
        fetcher_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Kelimenin bilinen en erken yazılı tanıklamasını bulur.

        :param live_entries: Fetcher'lardan gelen dil kayıtları.
        :param fetcher_results: Ham fetcher çıktıları; ``first_attestation``
            alanı taşıyanlar (ör. EtimolojiTürkçe) doğrudan kullanılır.
        :returns: ``verified`` alanı, bu kaydın A-HVP'de kanıt sayılıp
            sayılamayacağını belirtir. Kanıt yoksa tarih UYDURULMAZ.
        """
        w = (word or "").strip().lower()
        candidates: list[tuple[int, str, str]] = []

        # 1. Fetcher'ın doğrudan sağladığı tarihli tanıklama (en güvenilir)
        for res in fetcher_results or []:
            att = (res or {}).get("first_attestation")
            if att and att.get("year"):
                candidates.append((int(att["year"]), att.get("source", ""), "fetcher"))

        # 2. Dil kayıtlarının kaynak/ad alanlarında geçen bilinen tarihî eserler
        for entry in live_entries or []:
            haystack = " ".join(
                str(entry.get(k, "")) for k in ("lang_name", "meaning", "source", "word")
            )
            for pattern, year, label in DATED_SOURCES:
                if pattern.search(haystack):
                    candidates.append((year, label, "corpus"))

        if not candidates:
            logger.debug("'%s' için tarihli tanıklama bulunamadı", w)
            return {
                "word": w,
                "verified": False,
                "first_attestation_record": None,
                "first_attestation_year": None,
                "reason": "Veri katmanında tarihli bir yazılı tanıklama bulunamadı.",
            }

        year, source, origin = min(candidates, key=lambda c: c[0])
        return {
            "word": w,
            "verified": True,
            "first_attestation_record": source,
            "first_attestation_year": year,
            "evidence_origin": origin,
            "candidate_count": len(candidates),
        }

    @staticmethod
    def parse_year(text: str) -> int | None:
        """Serbest metinden yıl çıkarır (sayfa/cilt numaralarını dışlar)."""
        if not text:
            return None
        # "s. 456", "sayfa 130", "cilt 2", "p. 88", "nr. 12" bağlamlarını maskele
        masked = re.sub(r"\b(?:s|sf|sayfa|p|pp|cilt|c|nr|no|vol|II|III|IV)\.?\s*\d+", " ", text, flags=re.I)
        m = _YEAR_RE.search(masked)
        return int(m.group(1)) if m else None
