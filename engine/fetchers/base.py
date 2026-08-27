"""
Veri Toplayıcı Sözleşmesi ve Türki Dil Haritası (Fetcher Contract & Language Map)
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

# --- Türki diller ----------------------------------------------------------
# Kod -> Türkçe ad. README ve ARCHITECTURE "25 Türki dil" iddia ediyordu ama
# harita yalnızca 18 kod içeriyordu; README'de sayılan nog/kum/crh/kaa/cjs/ota
# eksikti ve bu dillerden gelen kayıtlar sessizce düşürülüyordu.
TURKIC_LANGUAGES_MAP: dict[str, str] = {
    "otk": "Eski Türkçe",
    "ota": "Osmanlı Türkçesi",
    "chg": "Çağatayca",
    "tr": "Türkiye Türkçesi",
    "az": "Azerbaycan Türkçesi",
    "gag": "Gagavuzca",
    "tk": "Türkmençe",
    "crh": "Kırım Tatarcası",
    "kk": "Kazakça",
    "kaa": "Karakalpakça",
    "ky": "Kırgızca",
    "nog": "Nogayca",
    "kum": "Kumukça",
    "krc": "Karaçay-Balkarca",
    "tt": "Tatarca",
    "ba": "Başkurtça",
    "uz": "Özbekçe",
    "ug": "Uygurca",
    "cv": "Çuvaşça",
    "sah": "Saha / Yakutça",
    "tyv": "Tuva Türkçesi",
    "alt": "Altay Türkçesi",
    "khk": "Hakasça",
    "cjs": "Şorca",
    "slq": "Salarca",
}

#: Toplam Türki dil sayısı. `cognate_alignment` gibi yayılım hesapları bu
#: değere bölmelidir; daha önce koda gömülü `25` sabiti kullanılıyordu ve
#: harita 18 dil içerdiği için oran matematiksel olarak %72'yi aşamıyordu.
TURKIC_LANGUAGE_COUNT = len(TURKIC_LANGUAGES_MAP)

# --- Wiktionary başlık eşlemesi -------------------------------------------
# Wiktionary bölüm başlıkları İNGİLİZCEDİR ("==Turkish==").
# `wiktionary.py` bunları TURKIC_LANGUAGES_MAP'in TÜRKÇE değerleriyle
# ("Türkiye Türkçesi") karşılaştırıyordu; hiçbir zaman eşleşmiyordu ve
# İngilizce Wiktionary kelime sayfası ayrıştırıcısı fiilen ölüydü.
WIKTIONARY_LANG_HEADERS: dict[str, str] = {
    "old turkic": "otk",
    "old turkish": "otk",
    "ottoman turkish": "ota",
    "chagatai": "chg",
    "turkish": "tr",
    "azerbaijani": "az",
    "south azerbaijani": "az",
    "north azerbaijani": "az",
    "gagauz": "gag",
    "turkmen": "tk",
    "crimean tatar": "crh",
    "kazakh": "kk",
    "karakalpak": "kaa",
    "kyrgyz": "ky",
    "kirghiz": "ky",
    "nogai": "nog",
    "kumyk": "kum",
    "karachay-balkar": "krc",
    "tatar": "tt",
    "bashkir": "ba",
    "uzbek": "uz",
    "northern uzbek": "uz",
    "uyghur": "ug",
    "uighur": "ug",
    "chuvash": "cv",
    "yakut": "sah",
    "sakha": "sah",
    "tuvan": "tyv",
    "altai": "alt",
    "southern altai": "alt",
    "khakas": "khk",
    "shor": "cjs",
    "salar": "slq",
}


def lang_code_from_wiktionary_header(header: str) -> str | None:
    """``"==Turkish=="`` gibi bir Wiktionary başlığından dil kodu çıkarır."""
    key = (header or "").strip().strip("=").strip().lower()
    return WIKTIONARY_LANG_HEADERS.get(key)


# --- Yazı sistemi tespiti --------------------------------------------------
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿ]")
_RUNIC = re.compile(r"[Ⴠ0-ჄF]" if False else r"[\U00010C00-\U00010C4F]")


def detect_script(word: str) -> str:
    """
    Kelimenin yazı sistemini döndürür: Latin | Cyrillic | Arabic | Runic.

    Daha önce bu üçlü koşul 6 ayrı fetcher'da kopyalanmıştı.
    """
    w = word or ""
    if _RUNIC.search(w):
        return "Runic"
    if _CYRILLIC.search(w):
        return "Cyrillic"
    if _ARABIC.search(w):
        return "Arabic"
    return "Latin"


class BaseFetcher(ABC):
    """
    Tüm veri toplayıcıların uyması gereken sözleşme.

    Sözleşme kuralı: ``fetch()`` **asla istisna fırlatmaz**. Başarısızlıkta
    ``empty_result()`` döndürür ve hatayı loglar. Böylece tek bir kaynağın
    çökmesi tüm aramayı düşürmez.
    """

    #: Bu kaynak yerel "seed" (tohum) veriden mi besleniyor, canlı bir
    #: servisten mi? Çıktıda `origin` alanı olarak raporlanır ve kullanıcıya
    #: elle yazılmış veriyle canlı kaynak ayrımını gösterir.
    is_seed_source: bool = False

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Fetcher kaynağının adı (örn. Wiktionary, Starling)."""

    @abstractmethod
    def fetch(self, word: str) -> dict[str, Any]:
        """
        Verilen kelime için Türki dillerdeki karşılıkları ve anlamları toplar.

        Dönüş formatı::

            {
                "root": {"proto_turkic": str, "meaning": str, "reconstruction_notes": str},
                "turkic_languages": [
                    {"lang_code": str, "lang_name": str, "word": str,
                     "meaning": str, "script": str}
                ]
            }
        """

    @staticmethod
    def empty_result() -> dict[str, Any]:
        """Boş sonuç iskeleti. Daha önce 21 fetcher'da birebir kopyalanmıştı."""
        return {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": [],
        }

    def make_entry(
        self,
        lang_code: str,
        word: str,
        meaning: str = "",
        *,
        lang_name: str | None = None,
        script: str | None = None,
    ) -> dict[str, Any]:
        """Sözleşmeye uygun tek bir dil kaydı üretir."""
        return {
            "lang_code": lang_code,
            "lang_name": lang_name or TURKIC_LANGUAGES_MAP.get(lang_code, lang_code),
            "word": word,
            "meaning": meaning,
            "script": script or detect_script(word),
            "origin": "seed" if self.is_seed_source else "live",
            "source": self.source_name,
        }
