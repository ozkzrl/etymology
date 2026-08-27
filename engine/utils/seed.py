"""
Tohum (Seed) Veri Yükleyici (Seed Data Loader)

Projede 9 fetcher, toplam 59 kelimelik elle yazılmış sözlükleri kod içinde
taşıyordu. ``cda0446`` commit'i "tüm hardcode kaldırıldı" dediği hâlde bu
sözlükler duruyor ve "Clauson EDPT & Sevortjan ЭСТЯ Veri Bankası" gibi
iddialı adlarla canlı kaynak süsü veriliyordu.

Artık bu veriler ``data/seed/`` altında JSON dosyalarında tutulur, kaynak
künyesi (provenance) taşır ve motor çıktısında ``origin: "seed"`` olarak
işaretlenir; kullanıcı canlı kaynakla tohum veriyi ayırt edebilir.

Dosya yoksa motor çökmez — o kaynak boş döner.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from engine.config import SEED_DIR
from engine.logging_setup import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=32)
def _load_file(rel_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = SEED_DIR / rel_path
    if not path.exists():
        logger.info("Tohum veri dosyası yok (kaynak boş dönecek): %s", path)
        return {}, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Tohum veri dosyası okunamadı: %s", path, exc_info=True)
        return {}, {}
    return payload.get("entries", {}), payload.get("_provenance", {})


def load_seed_entries(rel_path: str) -> dict[str, Any]:
    """Tohum dosyasındaki kelime -> kayıt eşlemesini döndürür."""
    entries, _ = _load_file(rel_path)
    return entries


def load_seed_provenance(rel_path: str) -> dict[str, Any]:
    """Tohum dosyasının kaynak künyesini döndürür."""
    _, provenance = _load_file(rel_path)
    return provenance


def seed_source_label(base_name: str, rel_path: str) -> str:
    """Kaynak adına tohum veri olduğunu açıkça ekler."""
    entries = load_seed_entries(rel_path)
    return f"{base_name} [yerel tohum veri, {len(entries)} kayıt]"


def clear_cache() -> None:
    """Testlerin tohum verisini yeniden yüklemesi için."""
    _load_file.cache_clear()
