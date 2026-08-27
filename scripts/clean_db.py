#!/usr/bin/env python3
"""
Veritabanı Temizlik Betiği (Database Cleanup)

`etymology.db` içinde geçmiş sürümlerden kalan kirli kayıtları temizler:

* ``<ctrl42>`` gibi LLM üretim artıkları (hem findings.full_finding_json
  hem turkic_entries.word içinde)
* ``lang_code='ai'`` yetim satırları — hiçbir fetcher artık bu kodu üretmiyor
* ``TURKIC_LANGUAGES_MAP`` dışındaki standart olmayan dil kodları

Kullanım::

    python scripts/clean_db.py [--dry-run] [--db PATH]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import DB_PATH  # noqa: E402
from engine.fetchers.base import TURKIC_LANGUAGES_MAP  # noqa: E402

ARTIFACT_RE = re.compile(r"<ctrl\d+>|\bAuth \(", re.I)
#: Motorun bilinçli olarak ürettiği sözde kodlar (silinmez)
PSEUDO_CODES = {"donor"}
#: Artık üretilmeyen, geçmiş sürümden kalan kodlar
ORPHAN_CODES = {"ai"}


def main() -> int:
    ap = argparse.ArgumentParser(description="etymology.db kirli kayıt temizliği")
    ap.add_argument("--db", default=str(DB_PATH), help="Veritabanı yolu")
    ap.add_argument("--dry-run", action="store_true", help="Sadece raporla, değiştirme")
    args = ap.parse_args()

    if not Path(args.db).exists():
        print(f"Veritabanı yok: {args.db}")
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    valid = set(TURKIC_LANGUAGES_MAP) | PSEUDO_CODES
    report: list[str] = []

    # 1. LLM artıkları — turkic_entries.word
    cur.execute("SELECT id, word FROM turkic_entries")
    dirty_entries = [r["id"] for r in cur.fetchall() if ARTIFACT_RE.search(r["word"] or "")]
    report.append(f"LLM artığı içeren turkic_entries satırı: {len(dirty_entries)}")

    # 2. Yetim dil kodları
    cur.execute("SELECT id, lang_code FROM turkic_entries")
    rows = cur.fetchall()
    orphan = [r["id"] for r in rows if r["lang_code"] in ORPHAN_CODES]
    unknown = sorted({r["lang_code"] for r in rows if r["lang_code"] not in valid and r["lang_code"] not in ORPHAN_CODES})
    report.append(f"Yetim 'ai' kodlu satır: {len(orphan)}")
    report.append(f"Standart dışı dil kodları: {unknown or 'yok'}")

    # 3. findings.full_finding_json içindeki artıklar
    cur.execute("SELECT id, query_word, full_finding_json FROM findings")
    dirty_findings = [(r["id"], r["query_word"]) for r in cur.fetchall() if ARTIFACT_RE.search(r["full_finding_json"] or "")]
    report.append(f"LLM artığı içeren findings kaydı: {len(dirty_findings)} {[w for _, w in dirty_findings]}")

    print("\n".join(report))

    if args.dry_run:
        print("\n--dry-run: hiçbir değişiklik yapılmadı.")
        conn.close()
        return 0

    if dirty_entries:
        cur.executemany("UPDATE turkic_entries SET word = ? WHERE id = ?",
                        [(ARTIFACT_RE.sub("", cur.execute("SELECT word FROM turkic_entries WHERE id=?", (i,)).fetchone()[0]).strip(), i)
                         for i in dirty_entries])
    if orphan:
        cur.executemany("DELETE FROM turkic_entries WHERE id = ?", [(i,) for i in orphan])
    for fid, _ in dirty_findings:
        cur.execute("SELECT full_finding_json FROM findings WHERE id = ?", (fid,))
        cleaned = ARTIFACT_RE.sub("", cur.fetchone()[0])
        cur.execute("UPDATE findings SET full_finding_json = ? WHERE id = ?", (cleaned, fid))

    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    print("\nTemizlik tamamlandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
