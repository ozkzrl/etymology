"""
EtimolojiTürkçe (Nişanyan Sözlük türevi) Veri Toplayıcı

Kelimenin etimolojik türeme zincirini ve **tarihli ilk yazılı tanıklamasını**
çıkarır. İlk tanıklama tarihi A-HVP kronolojik zaman kilidi aşamasının tek
gerçek girdisidir; daha önce bu alan uydurma bir cümleyle dolduruluyordu.

Sayfa yapısı (2026 itibarıyla doğrulandı)::

    <span class="ety1">           # bir türeme adımı
      <span class="ety1" title="Ses evrimi (evolution)">&lt;&lt;</span>
      <span class="ety2"><span title="Eski Türkçe (8.-11. yy ...)">ETü</span></span>
      <span class="ety4">teŋiz</span>
      <span class="ety3">göl veya deniz</span>
    </span>
    <h3>Tarihte En Eski Kaynak</h3>
    <p><i>teŋiz</i> "göl veya deniz" [ Divan-i Lugat-it Türk (1070) ]</p>
"""
from __future__ import annotations

import html as html_module
import re
import urllib.parse
from typing import Any

from engine import config
from engine.fetchers.base import BaseFetcher, detect_script
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get

logger = get_logger(__name__)

#: Sitedeki dil kısaltmaları -> (dil kodu, görünen ad).
#: Türki olmayan diller "donor" kodu ile alıntı kaynağı olarak işaretlenir.
LANG_ABBREV: dict[str, tuple[str, str]] = {
    "ETü": ("otk", "Eski Türkçe"),
    "OTü": ("chg", "Orta Türkçe / Çağatayca"),
    "TTü": ("tr", "Türkiye Türkçesi"),
    "YTü": ("tr", "Yeni Türkçe"),
    "OsmTü": ("ota", "Osmanlı Türkçesi"),
    "KTü": ("krc", "Kıpçak Türkçesi"),
    "Moğ": ("donor", "Moğolca"),
    "Ar": ("donor", "Arapça"),
    "Fa": ("donor", "Farsça"),
    "Yun": ("donor", "Yunanca"),
    "EYun": ("donor", "Eski Yunanca"),
    "Fr": ("donor", "Fransızca"),
    "İng": ("donor", "İngilizce"),
    "İt": ("donor", "İtalyanca"),
    "Rus": ("donor", "Rusça"),
    "Erm": ("donor", "Ermenice"),
    "Lat": ("donor", "Latince"),
    "Sogd": ("donor", "Soğdca"),
    "Çin": ("donor", "Çince"),
}

_STEP_RE = re.compile(
    r'<span class="ety1">\s*'
    r'<span[^>]*class="ety1"[^>]*>.*?</span>\s*'
    r'<span[^>]*class="ety2"[^>]*>(?P<lang>.*?)</span>\s*'
    r'<span class="ety4">(?P<form>.*?)</span>'
    r'(?P<rest>.*?)</span>',
    re.S,
)
_MEANING_RE = re.compile(r'<span class="ety3">(.*?)(?:</span>|\Z)', re.S)
_ATTEST_RE = re.compile(
    r"<i>(?P<form>[^<]+)</i>\s*(?:&quot;|\")(?P<meaning>[^\"&]*)(?:&quot;|\")\s*"
    r"\[\s*(?P<source>[^\]]*?)\s*\]",
    re.S,
)


def _text(html_fragment: str) -> str:
    """HTML parçasından düz metin çıkarır (tüm HTML varlıkları çözülür)."""
    t = re.sub(r"<[^>]+>", " ", html_fragment or "")
    t = html_module.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


class EtimolojiTurkceFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "EtimolojiTürkçe (Tarihli İlk Tanıklamalar)"

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = self.empty_result()
        if not word_clean:
            return result

        url = f"https://www.etimolojiturkce.com/kelime/{urllib.parse.quote(word_clean)}"
        html = http_get(url, timeout=config.HTTP_TIMEOUT_MEDIUM)
        if html is None:
            return result

        # Kelime sayfası yoksa site anasayfaya benzer bir içerik döndürür.
        if f"<h1>{word_clean.capitalize()}</h1>" not in html and f"<h1>{word_clean}</h1>" not in html.lower():
            logger.debug("EtimolojiTürkçe'de madde yok: %s", word_clean)
            return result

        self._parse_chain(html, result)
        self._parse_attestation(html, result)
        return result

    def _parse_chain(self, html: str, result: dict[str, Any]) -> None:
        """Türeme zincirindeki her adımı bir dil kaydına çevirir."""
        seen: set[tuple[str, str]] = set()
        for m in _STEP_RE.finditer(html):
            abbrev = _text(m.group("lang"))
            form = _text(m.group("form"))
            meaning_m = _MEANING_RE.search(m.group("rest"))
            meaning = _text(meaning_m.group(1)) if meaning_m else ""
            if not form:
                continue

            code, name = LANG_ABBREV.get(abbrev, ("donor", abbrev or "Bilinmeyen kaynak"))
            key = (code, form)
            if key in seen:
                continue
            seen.add(key)

            entry = self.make_entry(code, form, meaning, lang_name=name, script=detect_script(form))
            result["turkic_languages"].append(entry)

            # Eski Türkçe biçim varsa proto kök adayı olarak kaydet.
            if code == "otk" and not result["root"]["proto_turkic"]:
                result["root"]["proto_turkic"] = f"*{form}"
                if meaning:
                    result["root"]["meaning"] = meaning

    def _parse_attestation(self, html: str, result: dict[str, Any]) -> None:
        """'Tarihte En Eski Kaynak' bölümünden tarihli ilk tanıklamayı çıkarır."""
        idx = html.find("Tarihte En Eski Kaynak")
        if idx == -1:
            return
        segment = html[idx : idx + 2000]
        m = _ATTEST_RE.search(segment)
        if not m:
            return

        source = _text(m.group("source"))
        form = _text(m.group("form"))
        meaning = _text(m.group("meaning"))
        year_m = re.search(r"\((\d{3,4})\)", source)

        result["first_attestation"] = {
            "form": form,
            "meaning": meaning,
            "source": source,
            "year": int(year_m.group(1)) if year_m else None,
        }
        note = f"İlk tanıklama: {form}" + (f' "{meaning}"' if meaning else "") + f" [{source}]"
        result["root"]["reconstruction_notes"] = note
        if meaning and not result["root"]["meaning"]:
            result["root"]["meaning"] = meaning
