"""
Ortak Yazım / Karakter Sınıfı Yardımcıları (Shared Orthography Helpers)

Projede 9 ayrı modül şu karakter sınıfını kopyalıyordu::

    r'[^a-zçğıöşüа-яŕŋəäq]'

Bu sınıf ``а-я`` aralığını kullandığı için Türki dillerin Kiril alfabelerinde
geçen ``ё і ү ө ҫ ӑ ӗ ң ҡ һ ә ғ қ ұ ҳ`` gibi harfleri KAPSAMIYOR ve
Başkurtça / Çuvaşça / Kazakça kelimeler sessizce budanarak bozuk dizilere
dönüşüyordu (ör. "һыу" -> "ы").

Burada tek bir doğru sınıf tanımlanır ve tüm modüller bunu kullanır.
"""
from __future__ import annotations

import re

#: Latin tabanlı Türki alfabelerdeki harfler (Türkçe + Azerice + ortak transkripsiyon)
LATIN_TURKIC = "a-zçğıöşüâîûəäŕŗñŋśčžǰāīūōē"

#: Kiril tabanlı Türki alfabelerdeki harfler.
#: Temel Rus Kiril bloğu (а-я) + Türki dillere özgü genişletilmiş harfler.
CYRILLIC_TURKIC = (
    "а-яё"          # temel Kiril
    "әғқңөұүһٴ"     # Kazakça / Başkurtça
    "ҫӑӗҪ"          # Çuvaşça
    "җңүөһ"         # Tatarca
    "іӣӯ"           # Kırgızca / diğer
    "ҡҙҭҫ"          # Başkurtça
    "ӧӱ"            # Altayca / Hakasça
)

#: Arap alfabesi (Osmanlıca / Uygurca / Çağatayca)
ARABIC_TURKIC = "؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿"

#: Eski Türkçe runik (Orhun) yazısı
RUNIC_TURKIC = "\U00010c00-\U00010c4f"

#: Tüm Türki yazı sistemlerini kapsayan "korunacak karakterler" sınıfı.
ALL_TURKIC_CHARS = LATIN_TURKIC + CYRILLIC_TURKIC + ARABIC_TURKIC + RUNIC_TURKIC

#: Bu sınıfın DIŞINDA kalan her şeyi silmek için hazır desen.
NON_TURKIC_CHAR_RE = re.compile(f"[^{ALL_TURKIC_CHARS}]")

#: Latin harflerine normalize etme haritası (hizalama ve karşılaştırma için).
LATIN_NORMALISATION = {
    "ŕ": "ŕ", "ŗ": "r", "ŋ": "ŋ", "ñ": "ŋ", "ə": "e", "ä": "a", "ā": "a",
    "ī": "i", "ū": "u", "ō": "o", "ē": "e", "ś": "s", "č": "c", "ž": "z",
    "ǰ": "j", "q": "k", "â": "a", "î": "i", "û": "u",
    # Kiril -> Latin (kaba çeviri yazı; karşılaştırma amaçlı)
    "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "җ": "j", "з": "z", "и": "i", "і": "i", "й": "y", "к": "k", "қ": "k",
    "ҡ": "k", "л": "l", "м": "m", "н": "n", "ң": "ŋ", "о": "o", "ө": "ö", "п": "p",
    "р": "r", "с": "s", "ҫ": "s", "т": "t", "у": "u", "ұ": "u", "ү": "ü", "ф": "f",
    "х": "h", "һ": "h", "ҳ": "h", "ц": "ts", "ч": "ç", "ш": "ş", "щ": "ş", "ы": "ı",
    "ь": "", "ъ": "", "э": "e", "ә": "ä", "ю": "yu", "я": "ya", "ӑ": "a", "ӗ": "e",
    "ӧ": "ö", "ӱ": "ü", "ӣ": "i", "ӯ": "u", "ҙ": "z", "ҭ": "t",
}


def strip_non_turkic(text: str) -> str:
    """Türki yazı sistemleri dışındaki karakterleri siler."""
    return NON_TURKIC_CHAR_RE.sub("", (text or "").lower())


def to_comparison_form(text: str) -> str:
    """
    Kelimeyi diller arası karşılaştırma için ortak Latin biçimine indirger.

    Kiril ve özel fonetik işaretler Latin karşılıklarına çevrilir; böylece
    ``көз`` ile ``göz`` hizalanabilir hâle gelir.
    """
    t = (text or "").strip().lower().lstrip("*")
    out = []
    for ch in t:
        out.append(LATIN_NORMALISATION.get(ch, ch))
    joined = "".join(out)
    return re.sub(r"[^a-zçğıöşüŋŕĺ]", "", joined)


#: Proto-Türkçe rekonstrüksiyon seslerinin Ortak Türkçe'deki BEKLENEN refleksi.
#: Bir ata biçim ile modern biçimi karşılaştırırken ata sesi doğrudan değil,
#: beklenen refleksiyle kıyaslamak gerekir: *köŕ ile göz karşılaştırılırken
#: `ŕ` sesi `z` refleksine çevrilir, aksi hâlde düzenli bir denklik "fark"
#: olarak sayılır ve benzerlik skoru haksız yere düşer.
PROTO_REFLEXES = {
    "ŕ": "z",   # Lir-Şaz rotasizmi: PT *-ŕ > Ortak Türkçe -z
    "ĺ": "ş",   # Lambdaizm: PT *-ĺ > Ortak Türkçe -ş
    "ŋ": "n",   # PT *-ŋ- > çoğu kolda -n-
    "j": "y",   # PT *j- > Ortak Türkçe y-
}


def to_expected_reflex(text: str) -> str:
    """
    Ata biçimi, Ortak Türkçe'de beklenen refleksleriyle yazar.

    Karşılaştırma ve hizalama sırasında kullanılır; rekonstrüksiyon
    çıktısında ata sesler KORUNUR.
    """
    base = to_comparison_form(text)
    return "".join(PROTO_REFLEXES.get(ch, ch) for ch in base)
