"""
Ortak Test Altyapısı (Shared Test Fixtures)

Bu dosya daha önce yoktu; geçici veritabanı kurulumu iki ayrı test dosyasında
birebir kopyalanmıştı ve HTTP mock'lama hiç kullanılmıyordu (testler canlı ağa
çıkıyor, 112 saniye sürüyordu).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from engine.db.database import DatabaseManager
from engine.utils import network, seed

FIXTURE_DIR = Path(__file__).parent / "fixtures"
HTTP_FIXTURE_DIR = FIXTURE_DIR / "http"


@pytest.fixture(autouse=True)
def _isolate_network(monkeypatch):
    """
    Testlerin YANLIŞLIKLA canlı ağa çıkmasını engeller.

    Engelleme **soket düzeyindedir**: ``responses`` istekleri soket açmadan
    yakaladığı için mock'lanmış çağrılar geçer, gerçek çağrılar hata verir.
    (Daha yüksek bir katmanda engellemek ``responses``'i de bloke ederdi.)

    Ağ gerektiren testler ya ``responses`` ile mock'lar ya da
    ``engine/tests/live/`` altında ``@skipUnless`` ile işaretlenir.
    """
    if os.environ.get("ETY_LIVE") == "1":
        return

    import socket

    real_connect = socket.socket.connect

    def _blocked(self, address, *args, **kwargs):
        # Yerel bağlantılara izin ver (geçici dosya/sqlite yardımcıları)
        host = address[0] if isinstance(address, tuple) else str(address)
        if host in ("127.0.0.1", "::1", "localhost"):
            return real_connect(self, address, *args, **kwargs)
        raise AssertionError(
            f"Test canlı ağa çıkmaya çalıştı ({host}). `responses` ile mock'layın "
            "veya testi engine/tests/live/ altına taşıyın."
        )

    network.reset_session()
    monkeypatch.setattr(socket.socket, "connect", _blocked)


@pytest.fixture
def temp_db():
    """Geçici, izole SQLite veritabanı."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    try:
        yield db
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def seed_dir(tmp_path, monkeypatch):
    """İzole tohum veri dizini; testler gerçek data/seed'i kirletmez."""
    monkeypatch.setattr("engine.config.SEED_DIR", tmp_path)
    monkeypatch.setattr("engine.utils.seed.SEED_DIR", tmp_path)
    seed.clear_cache()
    yield tmp_path
    seed.clear_cache()


@pytest.fixture
def write_seed(seed_dir):
    """Tohum dosyası yazan yardımcı."""

    def _write(rel_path: str, entries: dict, provenance: dict | None = None) -> Path:
        path = seed_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "_schema": "turkic-etymology-seed/v1",
                    "_provenance": provenance or {"source": "test", "kind": "seed"},
                    "entries": entries,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        seed.clear_cache()
        return path

    return _write


@pytest.fixture
def sample_turkic_entries():
    """`göz` için gerçekçi, çok kollu akraba kayıt kümesi."""
    return [
        {"lang_code": "tr", "lang_name": "Türkiye Türkçesi", "word": "göz",
         "meaning": "görme organı", "script": "Latin", "source": "TDK", "origin": "live"},
        {"lang_code": "az", "lang_name": "Azerbaycan Türkçesi", "word": "göz",
         "meaning": "göz", "script": "Latin", "source": "Wiktionary", "origin": "live"},
        {"lang_code": "kk", "lang_name": "Kazakça", "word": "көз",
         "meaning": "göz", "script": "Cyrillic", "source": "Wiktionary", "origin": "live"},
        {"lang_code": "tt", "lang_name": "Tatarca", "word": "күз",
         "meaning": "göz", "script": "Cyrillic", "source": "Wiktionary", "origin": "live"},
        {"lang_code": "cv", "lang_name": "Çuvaşça", "word": "куҫ",
         "meaning": "göz", "script": "Cyrillic", "source": "Starling", "origin": "seed"},
        {"lang_code": "otk", "lang_name": "Eski Türkçe", "word": "köz",
         "meaning": "göz", "script": "Latin", "source": "DLT", "origin": "seed"},
        {"lang_code": "ky", "lang_name": "Kırgızca", "word": "көз",
         "meaning": "göz", "script": "Cyrillic", "source": "Wiktionary", "origin": "live"},
        {"lang_code": "ba", "lang_name": "Başkurtça", "word": "күҙ",
         "meaning": "göz", "script": "Cyrillic", "source": "Wiktionary", "origin": "live"},
    ]


@pytest.fixture
def sample_finding(sample_turkic_entries):
    """Veritabanı ve dışa aktarım testleri için tam bir bulgu nesnesi."""
    return {
        "query_word": "göz",
        "morphology": "Yalın Kök",
        "root": {
            "proto_turkic": "*köŕ",
            "meaning": "göz, görme organı",
            "reconstruction_notes": "Lir-Şaz rotasizmi",
        },
        "turkic_languages": sample_turkic_entries,
        "sources": ["TDK", "Wiktionary", "Starling"],
        "from_cache": False,
    }


def load_http_fixture(name: str) -> str:
    """Kayıtlı HTTP yanıtını okur."""
    path = HTTP_FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"HTTP fixture yok: {path}. `python scripts/record_fixtures.py --live` çalıştırın."
        )
    return path.read_text(encoding="utf-8")
