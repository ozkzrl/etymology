import re
from typing import Any

from engine.fetchers.base import BaseFetcher
from engine.utils.seed import load_seed_entries, seed_source_label

# Alıntı Kelimeler (Loanwords) Kaynak Dildeki Orijinal İmla, Anlam ve Kendi İçi Etimoloji Veri Bankası
#: Tohum (seed) veri. Kod içinde değil, data/seed/donor/donor_etymology.json dosyasında tutulur.
SEED_PATH = "donor/donor_etymology.json"
DONOR_ETYMOLOGY_DATABASE = load_seed_entries(SEED_PATH)

class LoanwordDonorEtymologyFetcher(BaseFetcher):
    #: Bu kaynak yerel tohum veriden beslenir, canlı bir servis DEĞİLDİR.
    is_seed_source = True

    @property
    def source_name(self) -> str:
        return seed_source_label("Alıntı Kelimeler Kaynak Dil Orijinal İmla ve Kendi İçi Etimoloji Veri Bankası", SEED_PATH)

    def fetch(self, word: str) -> dict[str, Any]:
        word_clean = word.strip().lower()
        result = {
            "root": {"proto_turkic": "", "meaning": "", "reconstruction_notes": ""},
            "turkic_languages": []
        }

        if word_clean in DONOR_ETYMOLOGY_DATABASE:
            data = DONOR_ETYMOLOGY_DATABASE[word_clean]
            donor_info = f"[{data['donor_lang']}] Orijinal İmla: {data['original_script']} | Kaynak Anlam: {data['donor_meaning']} | Kendi İçi Etimoloji: {data['internal_etymology']} | Geçiş Yörüngesi: {data['trajectory']}"
            result["root"]["reconstruction_notes"] = donor_info

            result["turkic_languages"].append({
                "lang_code": "donor",
                "lang_name": f"Kaynak Dil Etimolojisi ({data['donor_lang']})",
                "word": data["original_script"],
                "meaning": f"Kaynak Anlamı: {data['donor_meaning']} | Kendi İçi Türeyiş: {data['internal_etymology']}",
                "script": "Arabic" if re.search(r'[\u0600-\u06FF]', data["original_script"]) else ("Greek" if re.search(r'[\u0370-\u03FF]', data["original_script"]) else "Latin")
            })

        return result
