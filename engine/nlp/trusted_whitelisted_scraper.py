"""
Akademik Beyaz Liste Kazıyıcı ve Etimolojik Filtreleyici (Whitelisted Academic Scraper)
Amatör / uydurma etimoloji sitelerini engeller; sadece Nişanyan Sözlük, Kubbealtı Lugatim,
DergiPark Akademik Makaleler ve Wiktionary Etimoloji başlıklarını süzerek tam metin çeker.
"""
import re
import urllib.parse
import urllib.request

from engine import config
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get
from engine.utils.text import strip_html

logger = get_logger(__name__)

TRUSTED_DOMAINS = [
    "nisanyansozluk.com",
    "lugatim.com",
    "dergipark.org.tr",
    "wiktionary.org",
    "tdk.gov.tr",
    "islamansiklopedisi.org.tr",
    "archive.org"
]

def scrape_whitelisted_academic_sources(word: str) -> list[dict[str, str]]:
    """Sadece akademik beyaz listedeki etimoloji kaynaklarını sorgular ve tam metin çeker."""
    w = word.strip().lower()
    whitelisted_results = []

    # 1. Nişanyan Canlı Kazıma
    try:
        url = f"https://www.nisanyansozluk.com/kelime/{urllib.parse.quote(w)}"
        _body = http_get(url, timeout=config.HTTP_TIMEOUT_SHORT)
        if _body is not None:
            html = _body
            m_etym = re.search(r'class="etym[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            m_hist = re.search(r'class="hist[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)

            clean_etym = strip_html(m_etym.group(1)).strip() if m_etym else ""
            clean_hist = strip_html(m_hist.group(1)).strip() if m_hist else ""

            if clean_etym or clean_hist:
                whitelisted_results.append({
                    "domain": "nisanyansozluk.com",
                    "title": f"{w} - Nişanyan Etimolojik Sözlük",
                    "content": f"Köken: {clean_etym} | Tarihçe: {clean_hist}"
                })
    except Exception:
        logger.warning("dış kaynak işlenemedi", exc_info=True)
    # 2. DergiPark Akademik Makale Canlı Taraması
    try:
        url = f"https://dergipark.org.tr/tr/search?q={urllib.parse.quote(w)}+etimoloji"
        _body = http_get(url, timeout=config.HTTP_TIMEOUT_SHORT)
        if _body is not None:
            html = _body
            titles = re.findall(r'<a[^>]*class=\"[^\"]*card-title[^\"]*\"[^>]*>(.*?)</a>', html, re.DOTALL)
            clean_titles = [strip_html(t).strip() for t in titles[:2] if "doğrulayınız" not in t]
            if clean_titles:
                whitelisted_results.append({
                    "domain": "dergipark.org.tr",
                    "title": f"{w} Akademik Türkoloji Makaleleri",
                    "content": "; ".join(clean_titles)
                })
    except Exception:
        logger.warning("dış kaynak işlenemedi", exc_info=True)
    return whitelisted_results
