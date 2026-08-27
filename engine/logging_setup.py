"""
Merkezî Loglama Kurulumu (Central Logging Setup)

Proje daha önce 42 adet `except Exception: pass` bloğu içeriyordu ve tek bir
logging çağrısı yoktu; hangi veri kaynağının neden düştüğü görünmezdi.
Bu modül tüm katmanların ortak logger'ını sağlar.

Kullanım:
    from engine.logging_setup import get_logger
    logger = get_logger(__name__)
    ...
    except Exception:
        logger.warning("TDK GTS sorgusu başarısız: %s", word, exc_info=True)
"""
from __future__ import annotations

import logging
import os
import sys

from engine.config import LOG_LEVEL

_CONFIGURED = False


def configure_logging(level: str | int | None = None) -> None:
    """Kök logger'ı bir kez yapılandırır. Tekrar çağrılması güvenlidir."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved = level if level is not None else LOG_LEVEL
    root = logging.getLogger("engine")
    root.setLevel(resolved)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
        )
        root.addHandler(handler)

    # LingPy ve panphon import anında kök logger'a INFO seviyesinde yüzlerce
    # satır basıyor; bunları susturuyoruz.
    for noisy in ("lingpy", "panphon", "epitran", "urllib3", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """`engine.` ad alanı altında yapılandırılmış bir logger döndürür."""
    configure_logging()
    if not name.startswith("engine"):
        name = f"engine.{name}"
    return logging.getLogger(name)


def set_verbose(verbose: bool) -> None:
    """CLI `--verbose` bayrağı için seviye anahtarı."""
    configure_logging()
    logging.getLogger("engine").setLevel(logging.DEBUG if verbose else LOG_LEVEL)


# Testlerin ve CLI'ın ortam değişkeniyle sessizleştirebilmesi için
if os.environ.get("ETY_LOG_LEVEL"):
    configure_logging(os.environ["ETY_LOG_LEVEL"])
