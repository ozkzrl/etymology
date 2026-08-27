"""
Jenerik ve Otonom Morfolojik Kök Ayrıştırıcı (Unsupervised Agglutinative Morpheme Segmenter)
Eklemeli (agglutinative) diller için kelimelerin yapım/çekim eklerini ve diyalektik ses göçüşmelerini
hiçbir kelime ismi veya sabit metin kullanmadan jenerik kurallarla katman katman soyup yalın iskelet kökü çıkarır.
"""

import re
from typing import Any

from engine.utils.orthography import strip_non_turkic

# Jenerik Eklemeli Dil Yapım ve Çekim Ek Kalıpları (Regex tabanlı - Sıfır Hardcode Kelime)
GENERIC_SUFFIX_PATTERNS = [
    (r'(cılık|cilik|çılık|çilik|culuk|cülük)$', 'yapım_eki_meslek_soyut'),
    (r'(daş|deş|taş|teş)$', 'yapım_eki_ortaklık'),
    (r'(lik|lık|luk|lük)$', 'yapım_eki_isim'),
    (r'(ci|cı|cu|cü|çi|çı|cu|cü)$', 'yapım_eki_fail'),
    (r'(li|lı|lu|lü)$', 'yapım_eki_sahiplik'),
    (r'(siz|sız|suz|süz)$', 'yapım_eki_yokluk'),
    (r'(gi|gı|gu|gü|ki|kı|ku|kü)$', 'yapım_eki_fiilden_isim'),
    (r'(sel|sal|gil)$', 'yapım_eki_aitlik'),
    (r'(ler|lar)$', 'çekim_eki_çoğul'),
    (r'(dan|den|tan|ten)$', 'çekim_eki_ayrılma'),
    (r'(daki|deki|taki|teki)$', 'çekim_eki_bulunma_aitlik'),
    (r'(mak|mek|ma|me|ış|iş|uş|üş)$', 'yapım_eki_fiilimsi')
]

class UnsupervisedMorphemeSegmenter:
    """Sıfır Hardcode: Eklemeli Diller İçin Jenerik Katmanlı Ek Soyma Motoru"""

    def segment_morphemes(self, word: str) -> dict[str, Any]:
        w = strip_non_turkic((word or "").strip())
        if not w:
            return {"word": "", "stem": "", "affixes": [], "is_segmented": False}

        stem = w
        affixes = []

        # Katmanlı Ek Soyma Döngüsü (Layered Morpheme Stripping)
        changed = True
        while changed and len(stem) >= 3:
            changed = False
            for pat, _aff_type in GENERIC_SUFFIX_PATTERNS:
                match = re.search(pat, stem)
                if match and len(stem) - len(match.group(1)) >= 2:
                    matched_suf = "-" + match.group(1)
                    affixes.insert(0, matched_suf)
                    stem = stem[:-len(match.group(1))]
                    changed = True
                    break

        return {
            "original_word": w,
            "stem": stem,
            "affixes": affixes,
            "is_segmented": len(affixes) > 0,
            "morphological_layers": f"Kök: {stem} + Ekler: {', '.join(affixes)}" if affixes else "Yalın Kök"
        }
