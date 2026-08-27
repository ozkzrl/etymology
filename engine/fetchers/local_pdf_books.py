"""
Yerel PDF Türkoloji Kitapları İçi Tam Metin Tarama (Local PDF Full-Text Scanner)

``data/books/`` altındaki PDF dosyalarını **gerçekten** tarar ve aranan
kelimenin geçtiği bağlamları çıkarır.

Önceki sürüm
------------
Kaynak adı "Yerel PDF ... Metin İçi Tarama Motoru" olmasına ve ``os`` ile
``glob`` modüllerini import etmesine rağmen **hiçbir PDF okumuyordu**;
4 kelimelik elle yazılmış bir "kitap alıntısı" sözlüğü döndürüyordu.

Şimdi
-----
* ``pdfminer.six`` ile gerçek metin çıkarımı (opsiyonel: ``pip install -e ".[pdf]"``)
* Çıkarılan metin diske önbelleklenir; her aramada yeniden ayrıştırılmaz
* ``data/books/`` boşsa temiz biçimde boş sonuç döner (uydurma yapmaz)
* Geriye dönük uyumluluk için tohum alıntılar hâlâ okunur ama ``origin: "seed"``
  olarak işaretlenir
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from engine.config import BOOKS_DIR
from engine.fetchers.base import BaseFetcher
from engine.logging_setup import get_logger
from engine.utils.seed import load_seed_entries

logger = get_logger(__name__)

SEED_PATH = "lexicon/book_snippets.json"
LOCAL_BOOK_SNIPPETS = load_seed_entries(SEED_PATH)

#: Eşleşme çevresinde döndürülecek karakter sayısı
CONTEXT_CHARS = 160
#: Kitap başına azami eşleşme
MAX_MATCHES_PER_BOOK = 3


def _cache_path(pdf: Path) -> Path:
    digest = hashlib.blake2b(str(pdf.resolve()).encode(), digest_size=8).hexdigest()
    return BOOKS_DIR / ".text_cache" / f"{pdf.stem}-{digest}.txt"


def extract_pdf_text(pdf: Path) -> str:
    """PDF'ten düz metin çıkarır ve önbelleğe alır. pdfminer yoksa boş döner."""
    cache = _cache_path(pdf)
    if cache.exists() and cache.stat().st_mtime >= pdf.stat().st_mtime:
        try:
            return cache.read_text(encoding="utf-8")
        except OSError:
            logger.warning("PDF metin önbelleği okunamadı: %s", cache, exc_info=True)

    try:
        from pdfminer.high_level import extract_text
    except ImportError:
        logger.info(
            'pdfminer.six kurulu değil; PDF taraması devre dışı. Kurulum: pip install -e ".[pdf]"'
        )
        return ""

    try:
        text = extract_text(str(pdf)) or ""
    except Exception:
        logger.warning("PDF ayrıştırılamadı: %s", pdf, exc_info=True)
        return ""

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    except OSError:
        logger.warning("PDF metin önbelleği yazılamadı: %s", cache, exc_info=True)
    return text


class LocalPdfBooksFetcher(BaseFetcher):
    """``data/books/`` altındaki PDF'leri tarar; tohum alıntıları da ekler."""

    def __init__(self, books_dir: Path | None = None):
        self.books_dir = Path(books_dir) if books_dir else BOOKS_DIR

    @property
    def is_seed_source(self) -> bool:  # type: ignore[override]
        """Gerçek PDF varsa canlı kaynak, yoksa yalnızca tohum veri."""
        return not self._pdf_files()

    def _pdf_files(self) -> list[Path]:
        if not self.books_dir.exists():
            return []
        return sorted(p for p in self.books_dir.glob("**/*.pdf") if p.is_file())

    @property
    def source_name(self) -> str:
        pdfs = self._pdf_files()
        if pdfs:
            return f"Yerel PDF Türkoloji Kitapları ({len(pdfs)} kitap, tam metin taraması)"
        return f"Yerel Kitap Alıntıları [yerel tohum veri, {len(LOCAL_BOOK_SNIPPETS)} kayıt]"

    def fetch(self, word: str) -> dict[str, Any]:
        result = self.empty_result()
        word_clean = (word or "").strip().lower()
        if not word_clean:
            return result

        self._scan_pdfs(word_clean, result)
        self._add_seed_snippets(word_clean, result)
        return result

    def _scan_pdfs(self, word: str, result: dict[str, Any]) -> None:
        pattern = re.compile(rf"\b{re.escape(word)}\w*", re.I)
        for pdf in self._pdf_files():
            text = extract_pdf_text(pdf)
            if not text:
                continue
            matches = 0
            for m in pattern.finditer(text):
                start = max(0, m.start() - CONTEXT_CHARS // 2)
                end = min(len(text), m.end() + CONTEXT_CHARS // 2)
                context = re.sub(r"\s+", " ", text[start:end]).strip()
                result["turkic_languages"].append(
                    self.make_entry(
                        "otk",
                        word,
                        f"Kitap: {pdf.name} | Bağlam: …{context}…",
                        lang_name=f"Yerel PDF Tam Metin Taraması ({pdf.name})",
                        script="Latin",
                    )
                )
                if not result["root"]["reconstruction_notes"]:
                    result["root"]["reconstruction_notes"] = f"Yerel kitap kaydı: {pdf.name}"
                matches += 1
                if matches >= MAX_MATCHES_PER_BOOK:
                    break

    def _add_seed_snippets(self, word: str, result: dict[str, Any]) -> None:
        for item in LOCAL_BOOK_SNIPPETS.get(word, []):
            entry = self.make_entry(
                "otk",
                word,
                f"Kitap: {item.get('book', '?')} | Metin: {item.get('text', '')}",
                lang_name=f"Yerel Kitap Alıntısı (s. {item.get('page', '?')})",
                script="Latin",
            )
            entry["origin"] = "seed"
            result["turkic_languages"].append(entry)
            if not result["root"]["reconstruction_notes"]:
                result["root"]["reconstruction_notes"] = (
                    f"Tohum kitap kaydı: {item.get('book', '?')} (s. {item.get('page', '?')})"
                )
