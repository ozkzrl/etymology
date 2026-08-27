import re
import urllib.parse
import urllib.request
from typing import Any

from engine import config
from engine.fetchers.base import BaseFetcher
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get
from engine.utils.seed import load_seed_entries, seed_source_label
from engine.utils.text import strip_html

logger = get_logger(__name__)

# TDV İslam Ansiklopedisi (İSAM) Tarihi ve Etimolojik İndeks
#: Tohum (seed) veri. Kod içinde değil, data/seed/lexicon/isam.json dosyasında tutulur.
SEED_PATH = "lexicon/isam.json"
ISAM_ENCYCLOPEDIA_INDEX = load_seed_entries(SEED_PATH)

class IsamAnsiklopediFetcher(BaseFetcher):
    #: Bu kaynak yerel tohum veriden beslenir, canlı bir servis DEĞİLDİR.
    is_seed_source = True

    @property
    def source_name(self) -> str:
        return seed_source_label("TDV İslam Ansiklopedisi (İSAM Tarih ve Etimoloji Külliyatı)", SEED_PATH)

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        # 1. Dahili indekste kontrol
        if word_clean in ISAM_ENCYCLOPEDIA_INDEX:
            text = ISAM_ENCYCLOPEDIA_INDEX[word_clean]
            result["root"]["reconstruction_notes"] = text
            result["turkic_languages"].append({
                "lang_code": "otk",
                "lang_name": "TDV İSAM Ansiklopedisi (M.Ö. Hun & Orhun Kayıtları)",
                "word": word_clean,
                "meaning": text,
                "script": "Latin"
            })

        # 2. Canlı İSAM Web İsteği
        url = f"https://islamansiklopedisi.org.tr/{urllib.parse.quote(word_clean)}"
        try:
            _body = http_get(url, timeout=config.HTTP_TIMEOUT_MEDIUM)
            if _body is not None:
                html = _body
                ps = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
                for p in ps[:3]:
                    clean = strip_html(p).strip()
                    if ("Eski Türkçe" in clean or "Hun" in clean or "etimoloji" in clean or "kök" in clean) and len(clean) > 30:
                        clean_text = f"TDV İSAM: {clean[:200]}..."
                        result["root"]["reconstruction_notes"] = clean_text
                        result["turkic_languages"].append({
                            "lang_code": "otk",
                            "lang_name": "TDV İSAM Ansiklopedisi Metin Analizi",
                            "word": word_clean,
                            "meaning": clean[:150],
                            "script": "Latin"
                        })
                        break
        except Exception:
            logger.warning("%s: kaynak işlenemedi", self.source_name if hasattr(self, "source_name") else __name__, exc_info=True)
        return result
