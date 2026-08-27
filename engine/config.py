"""
Merkezî Yapılandırma (Central Configuration)

Projedeki tüm ağ adresleri, zaman aşımları, model adları, eşik değerleri ve
dosya yolları burada tek kaynaktan yönetilir. Her değer `ETY_` önekli bir ortam
değişkeniyle ezilebilir.

Bu modül, daha önce 32 ayrı `timeout=`, 32 gömülü URL ve 11 farklı User-Agent
olarak dağılmış olan sabitleri tek yerde toplar.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Yardımcılar -----------------------------------------------------------

def _env_str(name: str, default: str) -> str:
    return os.environ.get(f"ETY_{name}", default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(f"ETY_{name}", default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(f"ETY_{name}", default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"ETY_{name}")
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "evet"}


# --- Yollar ----------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(_env_str("DB_PATH", str(PROJECT_ROOT / "etymology.db")))
SCHEMA_PATH = PROJECT_ROOT / "engine" / "db" / "schema.sql"
SEED_DIR = Path(_env_str("SEED_DIR", str(PROJECT_ROOT / "data" / "seed")))
BOOKS_DIR = Path(_env_str("BOOKS_DIR", str(PROJECT_ROOT / "data" / "books")))

# --- Ağ --------------------------------------------------------------------

# Üç kademeli zaman aşımı. Daha önce 2–10 sn arası 32 farklı değer kullanılıyordu.
HTTP_TIMEOUT_SHORT = _env_float("HTTP_TIMEOUT_SHORT", 3.0)   # hızlı JSON API'ler
HTTP_TIMEOUT_MEDIUM = _env_float("HTTP_TIMEOUT_MEDIUM", 6.0)  # HTML kazıma
HTTP_TIMEOUT_LONG = _env_float("HTTP_TIMEOUT_LONG", 12.0)     # büyük sayfalar / wikitext

HTTP_MAX_RETRIES = _env_int("HTTP_MAX_RETRIES", 2)
HTTP_BACKOFF_BASE = _env_float("HTTP_BACKOFF_BASE", 0.3)
USER_AGENT = _env_str(
    "USER_AGENT",
    "TurkicEtymologyEngine/3.0 (academic research; +https://github.com/)",
)

# --- Arama motoru ----------------------------------------------------------

MAX_WORKERS = _env_int("MAX_WORKERS", 10)
# Varyant patlamasını sınırlar: 21 fetcher × N varyant = N×21 dış istek.
MAX_VARIANTS = _env_int("MAX_VARIANTS", 4)
CACHE_ENABLED = _env_bool("CACHE_ENABLED", True)
CACHE_TTL_SECONDS = _env_int("CACHE_TTL_SECONDS", 7 * 24 * 3600)
MAX_QUERY_LENGTH = _env_int("MAX_QUERY_LENGTH", 64)

# --- LLM (Ollama) ----------------------------------------------------------

OLLAMA_BASE_URL = _env_str("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_MODEL = _env_str("OLLAMA_MODEL", "qwen2.5:14b")
OLLAMA_TIMEOUT = _env_float("OLLAMA_TIMEOUT", 180.0)  # qwen2.5:14b yerel donanımda yavaş olabilir
OLLAMA_NUM_CTX = _env_int("OLLAMA_NUM_CTX", 1024)
OLLAMA_NUM_PREDICT = _env_int("OLLAMA_NUM_PREDICT", 250)
OLLAMA_TEMPERATURE = _env_float("OLLAMA_TEMPERATURE", 0.15)
# Kazınmış içeriğin isteme girebileceği azami karakter (prompt injection yüzeyini daraltır).
MAX_UNTRUSTED_CHARS = _env_int("MAX_UNTRUSTED_CHARS", 1500)

# --- REST API sunucusu -----------------------------------------------------

# Varsayılan olarak yalnızca yerel arayüz. Daha önce '' (0.0.0.0) idi.
API_HOST = _env_str("API_HOST", "127.0.0.1")
API_PORT = _env_int("API_PORT", 8000)
# CORS: virgülle ayrılmış origin listesi. '*' bilinçli bir tercih olmalıdır.
CORS_ALLOW_ORIGINS = tuple(
    o.strip() for o in _env_str("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
)
# Hata gövdesinde iç istisna metni döndürülsün mü (yalnızca geliştirme).
API_DEBUG_ERRORS = _env_bool("API_DEBUG_ERRORS", False)

# --- A-HVP hakem protokolü -------------------------------------------------

# Dört aşamanın ağırlıkları. Bir aşama kanıt üretemezse ağırlığı toplamdan
# düşülür ve skor katkıda bulunan aşamalara normalize edilir.
A_HVP_WEIGHTS = {
    "phonetic": _env_float("AHVP_W_PHONETIC", 0.35),
    "chronology": _env_float("AHVP_W_CHRONOLOGY", 0.30),
    "semantic": _env_float("AHVP_W_SEMANTIC", 0.15),
    "triangulation": _env_float("AHVP_W_TRIANGULATION", 0.20),
}

BADGE_THRESHOLDS = {
    "validated": _env_float("AHVP_T_VALIDATED", 0.75),
    "needs_review": _env_float("AHVP_T_NEEDS_REVIEW", 0.50),
}

# Kanıtlanan aşama ağırlığı bu oranın altındaysa rozet en fazla
# INSUFFICIENT_EVIDENCE olabilir. "Kanıt yoksa puan da yok" ilkesi.
MIN_EVIDENCE_COVERAGE = _env_float("AHVP_MIN_EVIDENCE_COVERAGE", 0.50)

# --- Kazıma güvenliği ------------------------------------------------------

TRUSTED_DOMAINS = tuple(
    d.strip()
    for d in _env_str(
        "TRUSTED_DOMAINS",
        "nisanyansozluk.com,lugatim.com,dergipark.org.tr,wiktionary.org,"
        "wikipedia.org,sozluk.gov.tr,tdk.gov.tr,islamansiklopedisi.org.tr,"
        "archive.org,etimolojiturkce.com,starling.rinet.ru",
    ).split(",")
    if d.strip()
)

# --- Loglama ---------------------------------------------------------------

LOG_LEVEL = _env_str("LOG_LEVEL", "WARNING")
