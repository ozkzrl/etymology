"""
Qwen2.5:14b Otonom Ajan Araştırma ve Bilimsel Tool Registry (Scientific & NLP Research Tools)
Etimoloji Motoru Ajanı için Doğrulama, Anti-Hallusinasyon ve Keşif Araçları.
"""
import json
import re
import urllib.parse
import urllib.request

from engine import config
from engine.logging_setup import get_logger
from engine.utils.morphology import NON_TURKIC_INITIAL_CONSONANTS, analyze_morphology
from engine.utils.network import fetch as http_get
from engine.utils.text import strip_html

logger = get_logger(__name__)

# --- DOĞRULAMA ARAÇLARI (VERIFICATION TOOLS) ---




# --- KEŞİF VE NLP ARAÇLARI (DISCOVERY & NLP TOOLS) ---


def tool_extract_suffixes(word: str) -> str:
    """Kelimeyi tarihsel yapım eklerine bölüp kökü ayrıştırır."""
    if not (word or "").strip():
        return "Morfotaktik Analiz: boş sorgu."
    stem, suffixes = analyze_morphology(word)
    if word[0] in NON_TURKIC_INITIAL_CONSONANTS and not suffixes:
        return f"Morfotaktik Analiz: '{word}' alıntı veya ağız biçimi olarak yalın yapıdadır."
    if suffixes:
        return f"Morfotaktik Analiz: Kök: '{stem}' | Tespit Edilen Ekler: {', '.join(suffixes)}"
    return f"Morfotaktik Analiz: '{stem}' yalın kök yapısındadır."




# --- WEB & AKADEMİK ARAMA ARAÇLARI (STRICT AUTO-CORRECT FILTERING) ---

def tool_web_search(query: str) -> list[dict[str, str]]:
    """Canlı web araması yapıp yeni akademik portallar, Vikipedi, Wiktionary ve Etimoloji sayfaları keşfeder (Multi-fallback)."""
    results = []
    # Boş/whitespace sorguda IndexError veriyordu.
    parts = (query or "").strip().lower().split()
    if not parts:
        logger.debug("Boş web arama sorgusu")
        return results
    word = parts[0]

    # 1. Fallback: Türkçe Wiktionary / Wikipedia API Araması
    try:
        wiki_url = f"https://tr.wiktionary.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(word)}&utf8=&format=json"
        _body = http_get(wiki_url, timeout=config.HTTP_TIMEOUT_SHORT)
        if _body is not None:
            data = json.loads(_body)
            search_items = data.get("query", {}).get("search", [])
            for item in search_items[:3]:
                title = item.get("title", "")
                snippet = re.sub(r'<[^>]+>', '', item.get("snippet", "")).strip()
                page_url = f"https://tr.wiktionary.org/wiki/{urllib.parse.quote(title)}"
                results.append({
                    "url": page_url,
                    "title": f"Wiktionary: {title}",
                    "snippet": snippet
                })
    except Exception:
        logger.warning("dış kaynak işlenemedi", exc_info=True)
    # 2. Fallback: Türkçe Wikipedia API Araması (Etimoloji Maddeleri)
    try:
        wp_url = f"https://tr.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(word + ' etimolojisi')}&utf8=&format=json"
        _body = http_get(wp_url, timeout=config.HTTP_TIMEOUT_SHORT)
        if _body is not None:
            data = json.loads(_body)
            search_items = data.get("query", {}).get("search", [])
            for item in search_items[:3]:
                title = item.get("title", "")
                snippet = re.sub(r'<[^>]+>', '', item.get("snippet", "")).strip()
                page_url = f"https://tr.wikipedia.org/wiki/{urllib.parse.quote(title)}"
                results.append({
                    "url": page_url,
                    "title": f"Vikipedi: {title}",
                    "snippet": snippet
                })
    except Exception:
        logger.warning("dış kaynak işlenemedi", exc_info=True)
    # 3. Fallback: Nişanyan / EtimolojiTürkçe Doğrudan Sayfa Araması
    try:
        et_url = f"https://www.etimolojiturkce.com/kelime/{urllib.parse.quote(word)}"
        _body = http_get(et_url, timeout=config.HTTP_TIMEOUT_SHORT)
        if _body is not None:
            html = _body
            if len(html) > 1500 and "Bulunamadı" not in html:
                clean_t = strip_html(html)
                clean_t = re.sub(r'\s+', ' ', clean_t).strip()
                results.append({
                    "url": et_url,
                    "title": f"EtimolojiTürkçe: {word}",
                    "snippet": clean_t[:300]
                })
    except Exception:
        logger.warning("dış kaynak işlenemedi", exc_info=True)
    # 4. Fallback: DuckDuckGo Lite / HTML Multi-Agent Search
    if len(results) < 2:
        try:
            clean_q = urllib.parse.quote(f"{word} etimoloji kökeni")
            ddg_url = f"https://html.duckduckgo.com/html/?q={clean_q}"
            _body = http_get(ddg_url, timeout=config.HTTP_TIMEOUT_SHORT)
            if _body is not None:
                html = _body
                links = re.findall(r'<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>', html, re.DOTALL)
                for link, title_text in links[:15]:
                    clean_title = strip_html(title_text).strip()
                    if len(clean_title) > 10 and word in clean_title.lower():
                        results.append({
                            "url": link,
                            "title": clean_title,
                            "snippet": f"{clean_title} etimolojik sözlük ve dilbilim kaydı."
                        })
        except Exception:
            logger.warning("dış kaynak işlenemedi", exc_info=True)
    return results



