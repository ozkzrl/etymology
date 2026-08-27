"""
Cross-Linguistic Data Formats (CLDF) Standart Aktarıcısı (CLDF Exporter)
Veritabanındaki etimoloji bulgularını ve akraba kelime dizilimlerini Max Planck Enstitüsü (CLLD)
tarafından tanımlanan uluslararası CLDF Wordlist / CognateSet standart CSV ve JSON meta formatında dışa aktarır.
"""

import csv
import io
from typing import Any


class CldfExporter:
    """CLDF Wordlist & CognateSet Standart Exporter"""

    def export_to_cldf(self, finding: dict[str, Any]) -> dict[str, str]:
        """
        Verilen etimoloji bulgusunu CLDF Wordlist, CognateTable ve ParameterTable CSV dizgilerine dönüştürür.
        """
        word = finding.get("query_word", "")
        turkic_entries = finding.get("turkic_languages", [])
        root_info = finding.get("root", {})
        proto_root = root_info.get("proto_turkic", word)

        # 1. Forms.csv (Wordlist)
        forms_output = io.StringIO()
        forms_writer = csv.writer(forms_output)
        forms_writer.writerow(["ID", "Language_ID", "Parameter_ID", "Form", "Value", "Segments"])

        for idx, entry in enumerate(turkic_entries, 1):
            lang_code = entry.get("lang_code", "tr")
            form_val = entry.get("word", "")
            segments = " ".join(list(form_val))
            forms_writer.writerow([f"form_{idx}", lang_code, f"param_{word}", form_val, form_val, segments])

        # 2. Cognates.csv (CognateSet)
        cog_output = io.StringIO()
        cog_writer = csv.writer(cog_output)
        cog_writer.writerow(["ID", "Form_ID", "Cognateset_ID", "Alignment", "Source"])

        for idx, entry in enumerate(turkic_entries, 1):
            cog_writer.writerow([f"cog_{idx}", f"form_{idx}", f"cogset_{proto_root}", entry.get("word", ""), "TurkicEtymologyEngine"])

        return {
            "query_word": word,
            "cldf_forms_csv": forms_output.getvalue(),
            "cldf_cognates_csv": cog_output.getvalue(),
            "metadata": {
                "cldfVersion": "1.2",
                "dc:conformsTo": "http://cldf.clld.org/v1.0/terms.rdf#Wordlist",
                "dc:title": f"Turkic Etymology CLDF Dataset - {word}"
            }
        }
