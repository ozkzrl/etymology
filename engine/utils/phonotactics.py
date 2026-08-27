"""
Türkçe Fonotaktik Kuralları (Turkish Phonotactics)

Bu kurallar projede birden çok yerde, **birbiriyle çelişen** biçimlerde
tanımlanmıştı:

* "Öz Türkçede bulunmayan söz başı ünsüzleri" iki farklı listeydi:
  ``morphology.py`` 6 harf (``f h p v j z``), ``loanword_classifier.py`` 10 harf
  (``f h p v j z r l m n``). Farklı modüller farklı listeyi kullanıyor,
  aynı kelime için çelişkili sonuç üretiyordu.
* Büyük ünlü uyumu kontrolü 4 ayrı yerde kopyalanmıştı.
* Arapça vezin desenleri ``advanced_tools.py`` ve ``loanword_classifier.py``
  içinde birebir aynı, Farsça sonek listeleri ise BİRBİRİNDEN SAPMIŞ hâldeydi
  (5 vs 7 sonek).
* Arapça vezin regexleri makronlu Latin harfleri (``ī``, ``ā``) bekliyordu ama
  girdi Türkçe imlaydı; bu yüzden hiçbir zaman eşleşmiyorlardı.
"""
from __future__ import annotations

import re

# --- Ünlüler ---------------------------------------------------------------
VOWELS = set("aeıioöuüâîû")
BACK_VOWELS = set("aıouâû")
FRONT_VOWELS = set("eiöüî")
ROUNDED_VOWELS = set("oöuü")

# --- Söz başı ünsüz kısıtları ---------------------------------------------
#: Öz Türkçe kelimelerin söz başında KESİNLİKLE bulunmayan ünsüzler.
#: (Türkolojide yerleşik kısıt; ünlem ve yansıma sözcükler istisnadır.)
STRICT_NON_TURKIC_INITIALS = frozenset("fhpvjzcğ")

#: Söz başında Öz Türkçe için ALIŞILMADIK olan, ancak istisnaları bulunan
#: ünsüzler. Alıntı göstergesi sayılır ama tek başına kanıt değildir.
WEAK_NON_TURKIC_INITIALS = frozenset("rlmn")

#: Geriye dönük uyumluluk için birleşik küme.
NON_TURKIC_INITIALS = STRICT_NON_TURKIC_INITIALS | WEAK_NON_TURKIC_INITIALS

#: Türkçe söz başında iki ünsüz yan yana gelmez (Batı alıntısı göstergesi).
INITIAL_CONSONANT_CLUSTERS = (
    "tr", "sp", "st", "kr", "pr", "dr", "gr", "sk", "str", "fl", "fr", "pl",
    "kl", "bl", "br", "cr", "sc", "sl", "sm", "sn", "sw", "tw", "kn", "ps", "ph",
)

# --- Alıntı dil kalıpları --------------------------------------------------
#: Arapça vezin kalıpları — TÜRKÇE İMLAYA uyarlanmış.
#: Eski sürüm makronlu (ī/ā) desenler kullandığı için hiç tetiklenmiyordu.
ARABIC_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"^mu[a-zçğıöşü]{2,}$", "mufa'al / mufa'il vezni"),
    (r"^m[eüu][a-zçğıöşü]{2,}$", "mef'ul / müfa'al vezni"),
    (r"^te[a-zçğıöşü]{3,}$", "tef'il vezni"),
    (r"^ist[iı][a-zçğıöşü]{2,}$", "istif'al vezni"),
    (r"^in[a-zçğıöşü]{3,}$", "infi'al vezni"),
    (r"^t[eaı][a-zçğıöşü]*[iı][a-zçğıöşü]$", "tef'îl vezni"),
    (r"[aeiıouöü]{1}[a-zçğıöşü]*iyet$", "-iyet masdar eki (Arapça)"),
    (r"[a-zçğıöşü]+iye$", "-iye eki (Arapça)"),
)

#: Farsça yapım ekleri — tek kaynak (iki kopya birbirinden sapmıştı).
PERSIAN_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("gâr", "-gâr / -kâr: yapan, eyleyen"),
    ("kâr", "-kâr: yapan, eyleyen"),
    ("gar", "-gar: yapan"),
    ("stan", "-stan: yer, ülke"),
    ("hane", "-hane: ev, yer"),
    # Türkçede söz içi h düşmesi: hasta+hane -> hastane, ecza+hane -> eczane
    ("ane", "-ane (< -hane): ev, yer"),
    ("dan", "-dan: kap, tutacak"),
    ("ban", "-ban: koruyan, bekçi"),
    ("baz", "-baz: oynayan"),
    ("perver", "-perver: besleyen, seven"),
    ("şinas", "-şinas: bilen, tanıyan"),
    ("name", "-name: yazı, mektup"),
)

WESTERN_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("syon", "-syon (Fransızca -tion)"),
    ("izm", "-izm (Fransızca -isme)"),
    ("izim", "-izim"),
    ("ist", "-ist"),
    ("loji", "-loji (Yunanca -logia)"),
    ("grafi", "-grafi (Yunanca -graphia)"),
    ("metre", "-metre"),
    ("skop", "-skop"),
    ("tör", "-tör (Fransızca -teur)"),
    ("zor", "-zör / -zor"),
)

GREEK_LATIN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"os$", "-os (Yunanca)"),
    (r"is$", "-is (Yunanca / Latince)"),
    (r"ya$", "-ya (Yunanca yer adı)"),
    (r"^ana[a-zçğıöşü]{3,}", "ana- öneki (Yunanca)"),
    (r"^anti[a-zçğıöşü]{2,}", "anti- öneki (Yunanca)"),
)


def has_vowel_harmony(word: str) -> bool:
    """
    Kelime büyük ünlü uyumuna uyuyor mu?

    Bu kontrol daha önce 4 ayrı modülde kopyalanmıştı.
    """
    vowels = [c for c in (word or "").lower() if c in VOWELS]
    if len(vowels) < 2:
        return True
    has_back = any(v in BACK_VOWELS for v in vowels)
    has_front = any(v in FRONT_VOWELS for v in vowels)
    return not (has_back and has_front)


def initial_consonant_violation(word: str) -> tuple[bool, str]:
    """
    Söz başı ünsüz kısıtı ihlali var mı? (ihlal_var, gerekçe)

    ``STRICT`` küme kesin ihlal, ``WEAK`` küme zayıf işaret sayılır.
    """
    w = (word or "").strip().lower()
    if not w:
        return False, ""
    first = w[0]
    if first in STRICT_NON_TURKIC_INITIALS:
        return True, f"Söz başı '{first}-' Öz Türkçe kelimelerde bulunmaz (kesin kısıt)"
    if first in WEAK_NON_TURKIC_INITIALS:
        return True, f"Söz başı '{first}-' Öz Türkçede alışılmadıktır (zayıf işaret)"
    return False, ""


def initial_cluster_violation(word: str) -> tuple[bool, str]:
    """Söz başında ünsüz kümesi var mı?"""
    w = (word or "").strip().lower()
    for cluster in INITIAL_CONSONANT_CLUSTERS:
        if w.startswith(cluster):
            return True, f"Söz başı ünsüz kümesi '{cluster}-' (Türkçe hece yapısına aykırı)"
    return False, ""


def match_arabic_pattern(word: str) -> str | None:
    w = (word or "").strip().lower()
    for pattern, desc in ARABIC_PATTERNS:
        if re.search(pattern, w):
            return desc
    return None


def match_suffix(word: str, table: tuple[tuple[str, str], ...]) -> str | None:
    w = (word or "").strip().lower()
    for suffix, desc in table:
        if w.endswith(suffix) and len(w) > len(suffix) + 1:
            return desc
    return None


def match_greek_latin_pattern(word: str) -> str | None:
    w = (word or "").strip().lower()
    for pattern, desc in GREEK_LATIN_PATTERNS:
        if re.search(pattern, w):
            return desc
    return None
