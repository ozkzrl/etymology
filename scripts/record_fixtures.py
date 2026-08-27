#!/usr/bin/env python3
"""
HTTP Fixture Kaydedici (HTTP Fixture Recorder)

Canlı kaynaklardan gerçek yanıtları bir kez indirir ve
``engine/tests/fixtures/http/`` altına kaydeder. Testler bu kayıtlı
yanıtları ``responses`` ile oynatır; böylece:

* testler ağsız çalışır (CI'da güvenilir)
* deterministiktir (kaynak sitedeki değişiklikten etkilenmez)
* hızlıdır (112 saniye -> saniyeler)

Kullanım::

    python scripts/record_fixtures.py --live
    python scripts/record_fixtures.py --live --word göz
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.utils.network import fetch  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "engine" / "tests" / "fixtures" / "http"

#: (fixture adı, URL şablonu). ``{w}`` yerine URL-kodlu kelime gelir.
SOURCES: dict[str, str] = {
    "tdk_gts_{w}.json": "https://sozluk.gov.tr/gts?ara={w}",
    "tdk_derleme_{w}.json": "https://sozluk.gov.tr/derleme?ara={w}",
    "tdk_tarama_{w}.json": "https://sozluk.gov.tr/tarama?ara={w}",
    "nisanyan_{w}.html": "https://www.nisanyansozluk.com/kelime/{w}",
    "etimolojiturkce_{w}.html": "https://www.etimolojiturkce.com/kelime/{w}",
    "wiktionary_en_{w}.json": (
        "https://en.wiktionary.org/w/api.php?action=parse&page={w}&format=json&prop=wikitext"
    ),
    "wiktextract_{w}.json": "https://en.wiktionary.org/api/rest_v1/page/definition/{w}",
    "archive_{w}.json": (
        "https://archive.org/advancedsearch.php?q={w}&fl%5B%5D=title&rows=3&output=json"
    ),
}


def record(word: str, overwrite: bool = False) -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for template, url_template in SOURCES.items():
        name = template.format(w=word)
        path = FIXTURE_DIR / name
        if path.exists() and not overwrite:
            print(f"  atlandı (var): {name}")
            continue
        url = url_template.format(w=urllib.parse.quote(word))
        body = fetch(url, timeout=15)
        if body is None:
            print(f"  BAŞARISIZ: {name} <- {url}")
            continue
        path.write_text(body, encoding="utf-8")
        print(f"  kaydedildi: {name} ({len(body)} bayt)")
        written += 1
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="Test için canlı HTTP yanıtlarını kaydeder")
    ap.add_argument("--live", action="store_true", required=True,
                    help="Canlı ağa çıkmayı onaylar")
    ap.add_argument("--word", action="append", default=None,
                    help="Kaydedilecek kelime (birden çok kez verilebilir)")
    ap.add_argument("--overwrite", action="store_true", help="Var olan fixture'ları yenile")
    args = ap.parse_args()

    words = args.word or ["deniz", "göz", "kitap"]
    total = 0
    for w in words:
        print(f"\n=== {w} ===")
        total += record(w, args.overwrite)
    print(f"\nToplam {total} fixture yazıldı -> {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
