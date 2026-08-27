"""
SQLite Kalıcılık Katmanı (Persistence Layer)

Bağlantı yönetimi notu
----------------------
``with sqlite3.connect(...) as conn:`` bloğu bağlantıyı **KAPATMAZ**; yalnızca
işlemi (transaction) yönetir. Önceki uygulama her ``save_finding`` /
``get_finding`` / ``list_findings`` çağrısında bir bağlantı sızdırıyordu.
Artık ``contextlib.closing`` ile bağlantı garantili kapatılır.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from typing import Any

from engine.config import DB_PATH, SCHEMA_PATH
from engine.logging_setup import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = str(DB_PATH)


class DatabaseManager:
    def __init__(self, db_path: str | os.PathLike[str] = DEFAULT_DB_PATH):
        self.db_path = str(db_path)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def connection(self):
        """İşlemi yöneten VE bağlantıyı kapatan bağlam yöneticisi."""
        conn = self.get_connection()
        try:
            with closing(conn), conn:
                yield conn
        except sqlite3.Error:
            logger.warning("Veritabanı işlemi başarısız: %s", self.db_path, exc_info=True)
            raise

    def init_db(self) -> None:
        """Veritabanını ve tabloları oluşturur (idempotent)."""
        if not os.path.exists(SCHEMA_PATH):
            logger.warning("Şema dosyası bulunamadı: %s", SCHEMA_PATH)
            return
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema_sql = f.read()
        with self.connection() as conn:
            conn.executescript(schema_sql)

    def save_finding(self, finding: dict[str, Any]) -> int:
        """
        Etimoloji bulgusunu standart formatta veritabanına kaydeder.
        Eğer kelime zaten varsa günceller.
        """
        query_word = finding.get("query_word", "").lower().strip()
        if not query_word:
            raise ValueError("query_word boş olamaz")

        root = finding.get("root", {})
        proto_turkic = root.get("proto_turkic", "")
        root_meaning = root.get("meaning", "")
        sources = finding.get("sources", [])
        turkic_languages = finding.get("turkic_languages", [])
        full_json = json.dumps(finding, ensure_ascii=False, indent=2)
        sources_json = json.dumps(sources, ensure_ascii=False)

        with self.connection() as conn:
            cursor = conn.cursor()

            # Var olan kaydı kontrol et
            cursor.execute("SELECT id FROM findings WHERE query_word = ?", (query_word,))
            row = cursor.fetchone()

            if row:
                finding_id = row["id"]
                cursor.execute("""
                    UPDATE findings
                    SET proto_turkic_root = ?, root_meaning = ?, sources_json = ?, full_finding_json = ?, created_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (proto_turkic, root_meaning, sources_json, full_json, finding_id))
                cursor.execute("DELETE FROM turkic_entries WHERE finding_id = ?", (finding_id,))
            else:
                cursor.execute("""
                    INSERT INTO findings (query_word, proto_turkic_root, root_meaning, sources_json, full_finding_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (query_word, proto_turkic, root_meaning, sources_json, full_json))
                finding_id = cursor.lastrowid

            # Türki dillerdeki kelime karşılıklarını ekle
            for entry in turkic_languages:
                cursor.execute("""
                    INSERT INTO turkic_entries (finding_id, lang_code, lang_name, word, meaning, script)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    finding_id,
                    entry.get("lang_code", ""),
                    entry.get("lang_name", ""),
                    entry.get("word", ""),
                    entry.get("meaning", ""),
                    entry.get("script", "Latin")
                ))

            return finding_id

    def get_finding(self, query_word: str, max_age_seconds: int | None = None) -> dict[str, Any] | None:
        """
        Kayıtlı etimoloji bulgusunu getirir.

        :param max_age_seconds: Verilirse, bu yaştan eski kayıtlar önbellek
            ıskalaması sayılır (``None`` döner). Önbellek TTL'i için kullanılır.
        """
        query_word = query_word.lower().strip()
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT full_finding_json, strftime('%s', created_at) AS created_ts "
                "FROM findings WHERE query_word = ?",
                (query_word,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        if max_age_seconds is not None:
            try:
                age = time.time() - float(row["created_ts"])
            except (TypeError, ValueError):
                age = None
            if age is not None and age > max_age_seconds:
                logger.debug("Önbellek kaydı eskimiş (%.0f sn): %s", age, query_word)
                return None
        try:
            return json.loads(row["full_finding_json"])
        except ValueError:
            logger.warning("Bozuk önbellek kaydı: %s", query_word, exc_info=True)
            return None

    def list_findings(self) -> list[dict[str, Any]]:
        """Tüm kaydedilmiş etimoloji bulgularını listeler."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, query_word, proto_turkic_root, root_meaning, created_at FROM findings ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
