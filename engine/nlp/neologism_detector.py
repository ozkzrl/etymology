"""
Neologizm ve Dil Devrimi Türetmesi Tespiti (Neologism Detector)

Kelimenin Cumhuriyet dönemi Dil Devrimi türetmesi olup olmadığını morfotaktik
kalıplarla saptar.

Düzeltilen sorunlar
-------------------
* ``[a-zçğıöşü]{2,}(im|ım|um|üm)$`` deseni ``resim``, ``hüküm``, ``takım``,
  ``kilim``, ``zulüm`` gibi ARAPÇA ALINTILARI "Cumhuriyet neolojizmi" sayıyor,
  ardından hipotez motoru bunlara 0.99 güvenle "TDK türetmesi" hipotezi
  kuruyordu. Bu ek artık yalnızca fiil kökünden türeme kanıtı varsa uygulanır.
* Desenlerde tekrar eden alternatifler vardı: ``(lik|lik|…)``,
  ``(reç|raç|raç|reç|…)``, ``(ci|cı|cu|cü|çi|çı|cu|cü)``.
* Bileşik türetmeler (``bilgisayar`` = bilgi + say- + -ar) hiç tespit
  edilmiyordu; motor ``bilgisayar`` için ``*bilgisayar`` diye bir Proto-Türkçe
  kök uyduruyordu.
"""
from __future__ import annotations

import re
from typing import Any

from engine.logging_setup import get_logger

logger = get_logger(__name__)

TURKISH_LETTER = "a-zçğıöşü"

#: Cumhuriyet dönemi özleştirme ekleri. Her giriş: (desen, açıklama, güçlü_mü)
#: "güçlü" ekler tek başına neologizm kanıtıdır; "zayıf" ekler ek kanıt ister.
NEOLOGISM_SUFFIX_PATTERNS: list[tuple[str, str, bool]] = [
    (rf"[{TURKISH_LETTER}]{{2,}}(sal|sel)$", "-sal/-sel eki (Fransızca -el/-al öykünmeli Dil Devrimi türetmesi)", True),
    (rf"[{TURKISH_LETTER}]{{2,}}(tay|tey)$", "-tay/-tey eki (Moğolca örnekli kurumsal neologizm)", True),
    (rf"[{TURKISH_LETTER}]{{2,}}(sel|sal)(lik|lık|luk|lük)$", "-sel/-sal + soyutluk eki birleşimi", True),
    (rf"[{TURKISH_LETTER}]{{2,}}(sel|sal)(ci|cı|cu|cü)$", "-sel/-sal + fail eki birleşimi", True),
    (rf"^(öz|ön|alt|üst|karşı|iç|dış)[{TURKISH_LETTER}]{{2,}}(lik|lık|sel|sal|güt|gün|gür|görü)$",
     "Ön-bileşenli Cumhuriyet dönemi türetmesi (öngörü, özgün vb.)", True),
    (rf"[{TURKISH_LETTER}]{{2,}}(men|man)$", "-men/-man eki ile meslek/unvan türetimi", False),
    (rf"[{TURKISH_LETTER}]{{2,}}(eç|aç|geç|gaç|raç|reç)$", "Fiilden araç adı eki (-eç / -geç / -aç)", False),
    (rf"[{TURKISH_LETTER}]{{3,}}(im|ım|um|üm)$", "-im/-ım eylem adı eki", False),
]

#: Bileşik neologizmlerde sık geçen ad kökleri (Dil Devrimi bileşikleri).
#: Kelime değil BİLEŞEN listesidir.
COMPOUND_HEADS: tuple[str, ...] = (
    "bilgi", "öz", "ön", "yer", "su", "gün", "yan", "iş", "söz", "yaz", "say",
    "uç", "bil", "ışık", "yıl", "ses", "göz", "el",
)

#: Bileşiğin ikinci öğesi olabilen fiil kökü + ek kalıpları
COMPOUND_TAILS: tuple[str, ...] = (
    "sayar", "yazar", "çalar", "gider", "yapar", "bakar", "tutar", "keser",
    "verir", "alır", "açar", "kapar", "bilir", "görür", "yazıcı", "sayıcı",
)


class NeologismDetector:
    def detect(self, word: str) -> dict[str, Any] | None:
        """
        Kelime bir Cumhuriyet dönemi türetmesi mi?

        :returns: Tespit edilirse ayrıntı sözlüğü, aksi hâlde ``None``.
            ``confidence`` alanı kanıt gücünü bildirir; sabit değildir.
        """
        w = (word or "").strip().lower()
        if not w or len(w) < 3:
            return None

        # 1. Bileşik türetme (bilgi+sayar, söz+cük vb.)
        compound = self._detect_compound(w)
        if compound:
            return compound

        # 2. Ek kalıpları
        for pattern, desc, strong in NEOLOGISM_SUFFIX_PATTERNS:
            if re.search(pattern, w):
                if not strong and not self._has_supporting_evidence(w):
                    logger.debug("Zayıf neologizm eki destek bulamadı: %s (%s)", w, desc)
                    continue
                # Zayıf eşleşmeler ADAY olarak bildirilir ama neologizm SAYILMAZ.
                # Aksi hâlde 'resim'/'takım' gibi Arapça alıntılar için hipotez
                # motoru "TDK türetmesi" hipotezi kuruyordu.
                return {
                    "word": w,
                    "is_neologism": bool(strong),
                    "is_candidate": True,
                    "confidence": 0.85 if strong else 0.40,
                    "evidence_strength": "strong" if strong else "weak",
                    "derivation_type": "Cumhuriyet dönemi / modern özleştirme türetmesi",
                    "etymology_details": (
                        f"Morfotaktik özleştirme kalıbı: {desc}. "
                        "Bu biçim tarihî metinlerde (13.-19. yy) doğrudan tanıklanmaz."
                    ),
                }
        return None

    def _detect_compound(self, w: str) -> dict[str, Any] | None:
        """``bilgisayar`` gibi ad + fiil bileşiklerini çözer."""
        for head in COMPOUND_HEADS:
            if not w.startswith(head) or len(w) <= len(head) + 2:
                continue
            tail = w[len(head):]
            for known_tail in COMPOUND_TAILS:
                if tail == known_tail:
                    return {
                        "word": w,
                        "is_neologism": True,
                        "confidence": 0.90,
                        "evidence_strength": "strong",
                        "derivation_type": "Cumhuriyet dönemi bileşik türetmesi",
                        "is_candidate": True,
                    "components": [head, known_tail],
                        "etymology_details": (
                            f"Bileşik yapı: '{head}' + '{known_tail}'. Dil Devrimi döneminde "
                            "ad + fiil kalıbıyla üretilmiş bileşik addır; tek parçalı bir "
                            "Proto-Türkçe kökü YOKTUR."
                        ),
                    }
        return None

    @staticmethod
    def _has_supporting_evidence(w: str) -> bool:
        """
        Zayıf ekler için ek kanıt arar.

        ``-im/-ım`` gibi ekler hem Türkçe eylem adı yapar (``se-çim``,
        ``bas-ım``) hem de Arapça alıntılarda bulunur (``resim``, ``hüküm``).
        Ayırt edici ölçüt: kalan kök Türkçe fonotaktiğine uyuyor mu?
        """
        from engine.utils.morphology import NON_TURKIC_INITIAL_CONSONANTS

        if w[0] in NON_TURKIC_INITIAL_CONSONANTS:
            return False
        # Büyük ünlü uyumu ihlali alıntı göstergesidir.
        vowels = [c for c in w if c in "aeıioöuü"]
        back = {c for c in vowels if c in "aıou"}
        front = {c for c in vowels if c in "eiöü"}
        return not (back and front)
