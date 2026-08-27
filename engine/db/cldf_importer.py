"""
CLDF Veri Kümesi İçe Alıcı (CLDF Dataset Importer)

Açık dilbilim veri kümelerini projeye alır:

* **WOLD** (World Loanword Database) — 395 dilde alıntı kelime ilişkileri
* **Wiktionary CLDF Loanword Bank**
* Herhangi bir CLDF Wordlist / CognateSet veri kümesi

Önceki durumda ``cldf_exporter.py`` yalnızca **dışa** aktarım yapıyordu; içe
alım hiç yoktu ve donör verisi 10 kelimelik elle yazılmış bir sözlükten
ibaretti.

Kullanım::

    python -m engine.db.cldf_importer /path/to/wold-cldf --target-language tur

Veri kümesi indirilmesi kullanıcıya bırakılmıştır (lisans ve boyut nedeniyle);
bu modül yerel bir CLDF dizinini okur.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from engine.config import SEED_DIR
from engine.logging_setup import get_logger

logger = get_logger(__name__)

#: CLDF FormTable'da aranan sütun adları (esnek eşleme)
FORM_COLUMNS = ("Form", "Value", "form", "value")
LANG_COLUMNS = ("Language_ID", "Language", "language_id")
PARAM_COLUMNS = ("Parameter_ID", "Concept_ID", "parameter_id")

#: WOLD'a özgü alıntı bilgisi sütunları
BORROWED_COLUMNS = ("Borrowed", "borrowed", "BorrowedScore", "Borrowed_Score")
SOURCE_WORD_COLUMNS = ("Source_Word_ID", "SourceWord_ID", "source_word_id")


def _pick(row: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if row.get(c):
            return row[c]
    return None


class CldfImporter:
    """Yerel bir CLDF veri kümesini okuyup donör tohum verisine dönüştürür."""

    def __init__(self, dataset_dir: str | Path):
        self.dir = Path(dataset_dir)

    def _find_table(self, *names: str) -> Path | None:
        for name in names:
            for candidate in (self.dir / name, self.dir / "cldf" / name):
                if candidate.exists():
                    return candidate
        # metadata üzerinden ara
        for meta in list(self.dir.glob("*.json")) + list(self.dir.glob("cldf/*.json")):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for table in data.get("tables", []):
                url = table.get("url", "")
                if any(n.lower() in url.lower() for n in names):
                    path = meta.parent / url
                    if path.exists():
                        return path
        return None

    def read_forms(self) -> list[dict[str, str]]:
        """FormTable (forms.csv) satırlarını okur."""
        path = self._find_table("forms.csv", "FormTable")
        if path is None:
            logger.warning("CLDF FormTable bulunamadı: %s", self.dir)
            return []
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def read_borrowings(self) -> list[dict[str, str]]:
        """BorrowingTable (borrowings.csv) satırlarını okur — WOLD için."""
        path = self._find_table("borrowings.csv", "BorrowingTable")
        if path is None:
            logger.info("CLDF BorrowingTable yok (veri kümesi alıntı bilgisi içermiyor olabilir)")
            return []
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def to_donor_entries(
        self, target_language: str = "tur", donor_names: dict[str, str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """
        Alıntı ilişkilerini projenin donör tohum şemasına çevirir.

        :param target_language: Hedef dilin CLDF ``Language_ID``'si (Türkçe için
            genellikle ``tur``).
        :param donor_names: ``Language_ID -> Türkçe dil adı`` eşlemesi.
        """
        forms = {row.get("ID"): row for row in self.read_forms()}
        borrowings = self.read_borrowings()
        names = donor_names or {}
        entries: dict[str, dict[str, Any]] = {}

        for row in borrowings:
            target_id = row.get("Target_Form_ID") or row.get("target_form_id")
            source_id = _pick(row, SOURCE_WORD_COLUMNS) or row.get("Source_Form_ID")
            target = forms.get(target_id)
            source = forms.get(source_id)
            if not target or not source:
                continue
            if _pick(target, LANG_COLUMNS) != target_language:
                continue

            word = (_pick(target, FORM_COLUMNS) or "").strip().lower()
            origin = (_pick(source, FORM_COLUMNS) or "").strip()
            donor_lang_id = _pick(source, LANG_COLUMNS) or "?"
            if not word or not origin:
                continue

            entries[word] = {
                "donor_lang": names.get(donor_lang_id, donor_lang_id),
                "original_script": origin,
                "donor_meaning": row.get("Comment", "") or _pick(source, ("Description",)) or "",
                "internal_etymology": row.get("Comment", ""),
                "trajectory": f"CLDF alıntı kaydı ({donor_lang_id} -> {target_language})",
                "_cldf_source": row.get("Source", ""),
            }

        logger.info("CLDF'den %d alıntı kaydı çıkarıldı", len(entries))
        return entries

    def write_seed(self, entries: dict[str, Any], filename: str = "donor/cldf_imported.json") -> Path:
        """Çıkarılan kayıtları tohum veri dizinine yazar."""
        out = SEED_DIR / filename
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "_schema": "turkic-etymology-seed/v1",
                    "_provenance": {
                        "source": f"CLDF veri kümesi: {self.dir}",
                        "kind": "cldf_import",
                        "note": "Harici CLDF veri kümesinden içe alınmıştır.",
                        "entry_count": len(entries),
                    },
                    "entries": entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("Tohum dosyası yazıldı: %s (%d kayıt)", out, len(entries))
        return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="CLDF veri kümesi içe alıcı (WOLD vb.)")
    ap.add_argument("dataset_dir", help="CLDF veri kümesi dizini")
    ap.add_argument("--target-language", default="tur", help="Hedef dil CLDF kodu (varsayılan: tur)")
    ap.add_argument("--out", default="donor/cldf_imported.json", help="Tohum dosyası adı")
    args = ap.parse_args()

    importer = CldfImporter(args.dataset_dir)
    entries = importer.to_donor_entries(args.target_language)
    if not entries:
        print("Alıntı kaydı bulunamadı. Veri kümesi bir BorrowingTable içeriyor mu?")
        return 1
    path = importer.write_seed(entries, args.out)
    print(f"{len(entries)} kayıt yazıldı: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
