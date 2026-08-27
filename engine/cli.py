import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from engine.db.cldf_exporter import CldfExporter
from engine.db.database import DatabaseManager
from engine.logging_setup import get_logger, set_verbose
from engine.nlp.hypothesis_validation_protocol import HypothesisValidationProtocol
from engine.search_engine import SearchEngine

logger = get_logger(__name__)


def print_finding_formatted(finding: dict[str, Any]) -> None:
    query_word = finding.get("query_word", "")
    morphology = finding.get("morphology", "Yalın Kök")
    root = finding.get("root", {})
    timeline = finding.get("timeline", [])
    related_cognates = finding.get("related_cognates", [])
    turkic_languages = finding.get("turkic_languages", [])
    sources = finding.get("sources", [])
    from_cache = finding.get("from_cache", False)
    ai_enrichment = finding.get("ai_agent_enrichment", "")
    web_sources = finding.get("discovered_web_sources", [])
    nlp_analysis = finding.get("nlp_analysis", {})

    # 1. GENEL BAŞLIK VE MORFOLOJİ ÖZETİ
    print("\n" + "═" * 80)
    print(f" 🔍 ETIMOLOJI BULGUSU VE KÖKEN RAPORU: {query_word.upper()} {'(Veritabanı Önbelleği)' if from_cache else ''}")
    print("═" * 80)
    print(f" 🧩 Morfoloji & Yapı         : {morphology}")
    print(f" 📌 Ana Kök / Rekonstrüksiyon: {root.get('proto_turkic', 'Bilinmiyor')}")
    print(f" 📖 Anlam                     : {root.get('meaning', 'Bilinmiyor')}")
    print(f" 📚 Kaynak Portföyü           : {', '.join(sources)}")

    # 2. A-HVP (YAPAY ZEKA HİPOTEZ DOĞRULAMA VE HAKEMLİK PROTOKOLÜ) ÇIKTISI
    proven_hypo = nlp_analysis.get("proven_hypothesis") or {}
    val_report = proven_hypo.get("validation_report") or {}
    if val_report:
        print("\n" + "─" * 80)
        print(" ⚖️  A-HVP (AI HYPOTHESIS VALIDATION PROTOCOL) HAKEM RAPORU")
        print("─" * 80)
        print(f"  • Hakem Kararı & Rozet      : {val_report.get('badge')}")
        print(f"  • Genel Güven Skoru          : {val_report.get('score_percentage')} ({val_report.get('final_confidence_score')})")
        print(f"  • Hipotez Türü              : {proven_hypo.get('hypothesis_type')}")
        print(f"  • Kaynak Form / Ata Biçim    : {proven_hypo.get('origin_form')}")

        stages = val_report.get("stage_breakdown", {})
        s1 = stages.get("stage1_phonetic_chain", {})
        s2 = stages.get("stage2_time_lock", {})
        s3 = stages.get("stage3_semantic_drift", {})
        s4 = stages.get("stage4_cognate_triangulation", {})

        print(f"  • 1. Fonetik Halka (IPA Kuralları): {'✅ GEÇTİ' if s1.get('is_valid') else '❌ İHLAL'} -> Eşleşen Ses Kuralları: {', '.join(s1.get('matched_rules', []))}")
        print(f"  • 2. Kronolojik Zaman Kilidi : {'✅ GEÇTİ' if s2.get('is_valid') else '❌ ANAKRONİZM'}")
        print(f"  • 3. Semantik Yörünge Sınırı : {'✅ GEÇTİ' if s3.get('is_valid') else '⚠️ UYARI'} -> {s3.get('reason')}")
        print(f"  • 4. Akraba Dil Triangulation: {'✅ GEÇTİ' if s4.get('is_valid') else '⚠️ EKSİK'} -> Numune Akrabalar: {', '.join(s4.get('sample_cognates', [])[:4])}")

        rejections = val_report.get("rejection_reasons", [])
        if rejections:
            print("\n  ⚠️  AKADEMİK HAKEM RED GEREKÇELERİ:")
            for rej in rejections:
                print(f"     ❌ {rej}")

    # 3. TÜRKİ DİLLERDEKİ ANLAMLARI VE KARŞILIKLARI
    print("\n" + "─" * 80)
    print(f" 🌍 TÜRKİ DİLLERDEKİ ANLAMLARI VE KARŞILIKLARI ({len(turkic_languages)} Dil/Katman)")
    print("─" * 80)

    if not turkic_languages:
        print("  ⚠️  Herhangi bir Türki dilde karşılık bulunamadı.")
    else:
        for entry in turkic_languages:
            lang_name = entry.get("lang_name", "")
            word = entry.get("word", "")
            meaning = entry.get("meaning", "")
            shift = entry.get("phonetic_shift", "")

            if entry.get("lang_code") == "ai":
                continue

            shift_info = f" [Ses Değişimi: {shift}]" if shift and shift != "Standart Lehçe Ses Uyumu" else ""
            print(f"  • {lang_name:<30} : {word:<24} [{'Anlam: ' + meaning if meaning else 'N/A'}]{shift_info}")

    # 4. CANLI KEŞFEDİLEN WEB KAYNAKLARI VE MAKALE BAĞLANTILARI
    if web_sources:
        print("\n" + "─" * 80)
        print(" 🌐 CANLI KEŞFEDİLEN WEB KAYNAKLARI VE MAKALE BAĞLANTILARI")
        print("─" * 80)
        for s in web_sources:
            url = s.get("url", "")
            title = s.get("title", "")
            snip = s.get("snippet", "")
            print(f"  🔗 [{title}]")
            print(f"     URL  : {url}")
            if snip:
                print(f"     Özet : {snip[:120]}...")

    # 5. TARİHSEL ZAMAN ÇİZELGESİ VE KÖK AKRABA SÖZCÜK AĞI
    if timeline:
        print("\n" + "─" * 80)
        print(" ⏳ TARİHSEL ZAMAN ÇİZELGESİ (EVRİM KRONOLOJİSİ)")
        print("─" * 80)
        for step in timeline:
            print(f"  • {step}")

    if related_cognates:
        print("\n" + "─" * 80)
        print(" 🔗 KÖK AKRABA SÖZCÜK AĞI")
        print("─" * 80)
        print(f"  • Aynı kökten türeyen akraba kelimeler: {', '.join(related_cognates)}")

    # 6. HESAPLAMALI NLP ALINTI & REKONSTRÜKSİYON ANALİZİ
    if nlp_analysis:
        loan_eval = nlp_analysis.get("loanword_classification", {})
        cog_eval = nlp_analysis.get("cognate_distribution", {})
        recon_eval = nlp_analysis.get("reconstruction", {})

        print("\n" + "─" * 80)
        print(" 🧬 HESAPLAMALI NLP ALINTI & REKONSTRÜKSİYON ANALİZİ")
        print("─" * 80)
        print(f"  • Sınıflandırma              : {loan_eval.get('classification')}")
        probs = loan_eval.get('probabilities', {})
        p_native = probs.get('p_native_turkic', 0) * 100
        p_east = probs.get('p_arabic_persian', 0) * 100
        p_med = probs.get('p_greek_latin', 0) * 100
        p_west = probs.get('p_western', 0) * 100
        print(f"  • Olasılık Dağılımı         : Öz Türkçe: %{p_native:.1f} | Doğu (Arap/Fars): %{p_east:.1f} | Akdeniz (Grek/Erm): %{p_med:.1f} | Batı: %{p_west:.1f}")
        print(f"  • 25 Lehçe Yayılımı Skorlama : %{cog_eval.get('spreading_ratio', 0)*100:.0f} ({cog_eval.get('assessment')})")
        print(f"  • Rekonstrüksiyon Değerlend: {recon_eval.get('reconstruction_notes')}")

    # 7. EN ALTA FİNAL SENTEZİ OLARAK: Qwen2.5 Otonom Yapay Zeka Ajanı Analizi
    if ai_enrichment:
        print("\n" + "┌" + "─" * 78 + "┐")
        print("│ 🤖 QWEN2.5 OTONOM BİLİMSEL AJAN AKIL YÜRÜTME & FİNAL SENTEZ PARAGRAFI  │")
        print("├" + "─" * 78 + "┤")
        lines = ai_enrichment.split("\n")
        for line in lines:
            if line.strip():
                wrapped_words = line.strip().split()
                current_line = "│ "
                for w in wrapped_words:
                    if len(current_line) + len(w) + 1 > 77:
                        print(f"{current_line:<79}│")
                        current_line = "│ " + w + " "
                    else:
                        current_line += w + " "
                if current_line.strip() != "│":
                    print(f"{current_line:<79}│")
            else:
                print("│" + " " * 78 + "│")
        print("└" + "─" * 78 + "┘")

    print("═" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Türki Diller Etimoloji Araştırma Motoru CLI")
    subparsers = parser.add_subparsers(dest="command", help="Komutlar")

    search_parser = subparsers.add_parser("search", help="Bir kelimenin etimolojisini ve Türki dillerdeki anlamlarını arar")
    search_parser.add_argument("word", type=str, help="Aranacak kelime (örn: su, deniz, göz, us, tetik, güzellik)")
    search_parser.add_argument("--json", action="store_true", help="Çıktıyı ham JSON formatında basar")
    search_parser.add_argument("--ai", action="store_true", help="Qwen2.5 otonom web araştırma ajanı ile derinleştirilmiş arama yap")
    search_parser.add_argument("--no-save", action="store_false", dest="save", help="Sonucu veritabanına kaydetme")

    validate_parser = subparsers.add_parser("validate", help="Bir etimoloji hipotezini A-HVP protokolü ile bilimsel olarak doğrular")
    validate_parser.add_argument("word", type=str, help="Hedef kelime")
    validate_parser.add_argument("--origin", type=str, default=None, help="Önerilen ata biçim / kök")
    validate_parser.add_argument("--donor", type=str, default="Öz Türkçe", help="Önerilen donör/kaynak dil")
    validate_parser.add_argument("--attestation", type=str, default="11. yüzyıl Divanü Lugati't-Türk", help="Yazılı ilk kayıt dönemi")

    bulk_parser = subparsers.add_parser("bulk", help="Bir metin dosyasındaki tüm kelimelerin etimolojisini topluca sorgular")
    bulk_parser.add_argument("--file", type=str, required=True, help="Kelimelerin bulunduğu metin dosyası")

    subparsers.add_parser("list", help="Veritabanına kaydedilmiş tüm kelimeleri listeler")

    show_parser = subparsers.add_parser("show", help="Veritabanındaki bir kelimenin bulgusunu detaylı gösterir")
    show_parser.add_argument("word", type=str, help="Gösterilecek kelime")
    show_parser.add_argument("--json", action="store_true", help="JSON formatında göster")

    export_parser = subparsers.add_parser(
        "export", help="Kayıtlı bulguyu CLDF (Cross-Linguistic Data Formats) olarak dışa aktarır"
    )
    export_parser.add_argument("word", type=str, help="Dışa aktarılacak kelime")
    export_parser.add_argument("--out", type=str, default=None, help="Çıktı dizini (varsayılan: cldf_export/)")

    parser.add_argument("--verbose", "-v", action="store_true", help="Ayrıntılı log çıktısı")

    args = parser.parse_args()
    set_verbose(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(1)

    db_manager = DatabaseManager()
    engine = SearchEngine(db_manager=db_manager)

    if args.command == "search":
        try:
            if args.ai:
                print("🤖 Qwen2.5 Otonom Web Keşif Ajanı Devrede... (Derin Web & Makale Taraması Yapılıyor)")
            finding = engine.search(args.word, save_to_db=args.save, use_qwen_agent=args.ai)
            if args.json:
                print(json.dumps(finding, ensure_ascii=False, indent=2))
            else:
                print_finding_formatted(finding)
        except Exception as e:
            logger.error("Arama başarısız: %s", args.word, exc_info=True)
            print(f"❌ Arama başarısız: {type(e).__name__}. Ayrıntı için --verbose kullanın.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "validate":
        protocol = HypothesisValidationProtocol()
        origin_form = args.origin or args.word
        hypothesis = {
            "hypothesis_type": f"Özel Etimoloji Hipotezi ({args.donor})",
            "origin_form": origin_form,
            "donor_language": args.donor,
            "proof_summary": f"Kullanıcı Hipotezi: {args.donor} kökenli {origin_form}",
            "historical_meaning": args.word
        }
        attestation = {"first_attestation_record": args.attestation}

        report = protocol.validate_hypothesis(args.word, hypothesis, attestation)
        print("\n" + "═" * 80)
        print(f" ⚖️  A-HVP AKADEMİK DOĞRULAMA VE HAKEM HİPOTEZİ RAPORU: {args.word.upper()}")
        print("═" * 80)
        print(f"  • Hakem Kararı & Rozet      : {report['badge']}")
        print(f"  • Hakem Skoru (% Yüzde)      : {report['score_percentage']}")
        print(f"  • Önerilen Ata Kök          : {origin_form}")
        print(f"  • Önerilen Donör Dil         : {args.donor}")
        print(f"  • İlk Yazılı Tanıklama      : {args.attestation}")

        stages = report.get("stage_breakdown", {})
        s1 = stages.get("stage1_phonetic_chain", {})
        s2 = stages.get("stage2_time_lock", {})
        s3 = stages.get("stage3_semantic_drift", {})
        s4 = stages.get("stage4_cognate_triangulation", {})

        print("\n  📌 5 KADEMELİ HAKEM AŞAMA DETAYLARI:")
        print(f"   1. Fonetik Halka (IPA Evrimi): {'✅ GEÇTİ' if s1.get('is_valid') else '❌ İHLAL'} -> {', '.join(s1.get('matched_rules', []))}")
        print(f"   2. Kronolojik Zaman Kilidi  : {'✅ GEÇTİ' if s2.get('is_valid') else '❌ ANAKRONİZM'}")
        print(f"   3. Diyakronik Semantik Sınır: {'✅ GEÇTİ' if s3.get('is_valid') else '⚠️ UYARI'} -> {s3.get('reason')}")
        print(f"   4. Akraba Dil Triangulation : {'✅ GEÇTİ' if s4.get('is_valid') else '⚠️ EKSİK'} -> Numune: {', '.join(s4.get('sample_cognates', [])[:4])}")

        rejections = report.get("rejection_reasons", [])
        if rejections:
            print("\n  ⚠️  AKADEMİK HAKEM RED GEREKÇELERİ:")
            for rej in rejections:
                print(f"     ❌ {rej}")
        print("═" * 80 + "\n")

    elif args.command == "bulk":
        if not os.path.exists(args.file):
            print(f"❌ Dosya bulunamadı: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
        print(f"\n📦 TOPLU ETIMOLOJI TARAMASI BAŞLATILDI ({len(words)} Kelime)\n")
        for i, w in enumerate(words, 1):
            print(f"[{i}/{len(words)}] Aratılıyor: {w} ...")
            finding = engine.search(w, save_to_db=True)
            print(f"  ✓ Tamamlandı: {w} (Kök: {finding['root']['proto_turkic']})")
        print("\n✅ Tüm toplu arama sonuçları veritabanına kaydedildi.\n")

    elif args.command == "list":
        findings = db_manager.list_findings()
        print(f"\n📂 VERİTABANINDA KAYITLI ETIMOLOJİ BULGULARI ({len(findings)} Kayıt)")
        print("-" * 75)
        for f in findings:
            print(f"  • {f['query_word']:<15} | Kök: {f['proto_turkic_root']:<12} | Anlam: {f['root_meaning']:<25} | Tarih: {f['created_at']}")
        print("-" * 75 + "\n")

    elif args.command == "show":
        finding = db_manager.get_finding(args.word)
        if not finding:
            print(f"❌ '{args.word}' kelimesi veritabanında bulunamadı.", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(finding, ensure_ascii=False, indent=2))
        else:
            print_finding_formatted(finding)

    elif args.command == "export":
        finding = db_manager.get_finding(args.word)
        if not finding:
            print(f"❌ '{args.word}' kelimesi veritabanında bulunamadı. Önce `search` çalıştırın.", file=sys.stderr)
            sys.exit(1)
        out_dir = Path(args.out) if args.out else Path("cldf_export")
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle = CldfExporter().export_to_cldf(finding)
        written = []
        file_map = {
            "forms.csv": bundle["cldf_forms_csv"],
            "cognates.csv": bundle["cldf_cognates_csv"],
            "cldf-metadata.json": json.dumps(bundle["metadata"], ensure_ascii=False, indent=2),
        }
        for name, content in file_map.items():
            path = out_dir / name
            path.write_text(content, encoding="utf-8")
            written.append(str(path))
        print(f"\n📦 CLDF dışa aktarımı tamamlandı ({len(written)} dosya):")
        for w in written:
            print(f"  • {w}")
        print()

if __name__ == "__main__":
    main()
