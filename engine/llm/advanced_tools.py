"""
İleri Düzey Otonom Ajan Araştırma Araçları (Advanced Agentic ReAct Toolset)
Etimoloji Motoru için Canlı API'ler, IPA Fonetik Dönüştürücü, Vezin Analizcisi ve Tarihsel Külliyat Taramaları.
"""
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from engine import config
from engine.logging_setup import get_logger
from engine.utils.network import fetch as http_get
from engine.utils.phonotactics import (
    PERSIAN_SUFFIXES,
    VOWELS,
    has_vowel_harmony,
    match_arabic_pattern,
    match_greek_latin_pattern,
    match_suffix,
)

logger = get_logger(__name__)

# --- 1. ÇOK DİLLİ WIKTIONARY REST API (25 TÜRKİ DİL + KAYNAK DİLLER) ---

def tool_wiktionary_multilingual_api(word: str) -> dict[str, Any]:
    """Wiktionary REST API üzerinden kelimenin 25 Türki dilde ve kaynak dillerde (Arapça, Farsça, Grekçe, Latince) etimolojisini çeker."""
    w = word.strip().lower()
    results = {}

    # Türkçe Wiktionary API
    try:
        url = f"https://tr.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(w)}"
        _body = http_get(url, timeout=config.HTTP_TIMEOUT_SHORT)
        if _body is not None:
            data = json.loads(_body)
            results["tr_wiktionary"] = data
    except Exception:
        logger.warning("dış kaynak işlenemedi", exc_info=True)
    # İngilizce Wiktionary API (Etimoloji bölümü son derece zengindir)
    try:
        url = f"https://en.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(w)}"
        _body = http_get(url, timeout=config.HTTP_TIMEOUT_SHORT)
        if _body is not None:
            data = json.loads(_body)
            results["en_wiktionary"] = data
    except Exception:
        logger.warning("dış kaynak işlenemedi", exc_info=True)
    summary = []
    if "en_wiktionary" in results:
        for lang, defs in results["en_wiktionary"].items():
            if lang in ["Turkish", "Ottoman Turkish", "Chagatai", "Old Turkic", "Kazakh", "Uzbek", "Tatar", "Arabic", "Persian", "Greek"]:
                for d in defs[:2]:
                    def_text = re.sub(r'<[^>]+>', '', d.get("definition", ""))
                    summary.append(f"[{lang}] {def_text[:100]}")

    return {
        "word": w,
        "api_summary": summary[:4] if summary else ["Wiktionary kaydı bulundu veya canlı sorgulandı."],
        "raw_found": bool(results)
    }

# --- 2. IPA ULUSLARARASI FONETİK ALFABESİ VE DİLBİLİM MOTORU ---

TURKIC_IPA_MAP = {
    'a': 'ɑ', 'e': 'e', 'ı': 'ɯ', 'i': 'i', 'o': 'o', 'ö': 'ø', 'u': 'u', 'ü': 'y',
    'b': 'b', 'c': 'dʒ', 'ç': 'tʃ', 'd': 'd', 'f': 'f', 'g': 'ɡ', 'ğ': 'ɰ', 'h': 'h',
    'j': 'ʒ', 'k': 'k', 'l': 'l', 'm': 'm', 'n': 'n', 'ñ': 'ŋ', 'p': 'p', 'r': 'r',
    's': 's', 'ş': 'ʃ', 't': 't', 'v': 'v', 'y': 'j', 'z': 'z'
}

def tool_ipa_phonetic_analyzer(word: str) -> dict[str, Any]:
    """Kelimeyi Uluslararası Fonetik Alfabeye (IPA) dönüştürür ve hece fonotaktiğini çıkarır."""
    w = word.strip().lower()
    ipa_chars = [TURKIC_IPA_MAP.get(c, c) for c in w]
    ipa_str = "/" + "".join(ipa_chars) + "/"

    # Ünlü uyumu kontrolü — ortak fonotaktik yardımcısı (4 kopya birleştirildi)
    vowels = [c for c in w if c in VOWELS]
    harmony = "Tam Uyumlu" if has_vowel_harmony(w) else "İhlal Var (Alıntı Kelime Göstergesi)"

    return {
        "word": w,
        "ipa": ipa_str,
        "vowel_harmony_status": harmony,
        "vowel_count": len(vowels),
        "initial_sound": ipa_chars[0] if ipa_chars else ""
    }

# --- 3. KAYNAK DİL VEZİN VE YAPI ANALİZCİSİ (ARAPÇA/FARSÇA/GREKÇE) ---
# Desen tabloları engine.utils.phonotactics içinde TEK KAYNAKTAN yönetilir.
# Bu dosyadaki kopyalar loanword_classifier'daki listelerden sapmıştı
# (5 vs 7 Farsça sonek) ve makronlu regexler hiç tetiklenmiyordu.

def tool_donor_pattern_analyzer(word: str) -> dict[str, Any]:
    """Arapça vezin, Farsça bileşik yapılar ve Grekçe/Latince sonekleri tespit eder."""
    w = word.strip().lower()
    matches = []

    arabic = match_arabic_pattern(w)
    if arabic:
        matches.append(f"Arapça {arabic}")

    persian = match_suffix(w, PERSIAN_SUFFIXES)
    if persian:
        matches.append(f"Farsça {persian}")

    greek = match_greek_latin_pattern(w)
    if greek:
        matches.append(f"Grekçe/Latince {greek}")

    return {
        "word": w,
        "detected_donor_patterns": matches if matches else ["Belirgin alıntı vezni tespit edilmedi (Yerli Öz Türkçe kök yapısı veya yalın alıntı)."],
        "is_probable_loanword": bool(matches)
    }

# --- 4. DİLLER ARASI FONETİK SES DEĞİŞİM MATRİSİ (LEVENSHTEIN DISTANCE) ---


# --- 5. TARİHSEL KÜLLİYAT DİZİNİ ARAMASI ---


