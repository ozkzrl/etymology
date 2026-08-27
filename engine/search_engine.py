import concurrent.futures
import re
import time
from functools import lru_cache
from typing import Any

from engine import config
from engine.db.database import DatabaseManager
from engine.db.graph_database import GraphDatabaseManager
from engine.fetchers.academic_turkology import AcademicTurkologyFetcher
from engine.fetchers.archive_org import ArchiveOrgFetcher
from engine.fetchers.base import TURKIC_LANGUAGES_MAP, BaseFetcher
from engine.fetchers.etimoloji_turkce import EtimolojiTurkceFetcher
from engine.fetchers.historical_modern import HistoricalModernLexiconFetcher
from engine.fetchers.isam_ansiklopedi import IsamAnsiklopediFetcher
from engine.fetchers.loanword_donor_etymology import LoanwordDonorEtymologyFetcher
from engine.fetchers.local_pdf_books import LocalPdfBooksFetcher
from engine.fetchers.multilang_wiktionary import MultiLangWiktionaryFetcher
from engine.fetchers.osmanlica_lugat import OsmanlicaLugatFetcher
from engine.fetchers.starling import StarlingFetcher
from engine.fetchers.tdk_historical import TdkDerlemeFetcher, TdkTaramaFetcher
from engine.fetchers.tdk_nisanyan import NisanyanFetcher, TdkFetcher
from engine.fetchers.tietze_altaica import TietzeAltaicaFetcher
from engine.fetchers.turkic_national_dictionaries import TurkicNationalDictionariesFetcher
from engine.fetchers.wiktextract_local import WiktextractFetcher
from engine.fetchers.wiktionary import WiktionaryFetcher
from engine.llm.qwen_agent import QwenEtymologyAgent
from engine.logging_setup import get_logger
from engine.nlp.cldf_lingpy_aligner import CldfLingPyAligner
from engine.nlp.cognate_alignment import CognateAlignmentEngine
from engine.nlp.cognate_clustering import CognateClusterEngine
from engine.nlp.derivation_network import DerivationNetworkBuilder
from engine.nlp.diachronic_semantic_engine import DiachronicSemanticEngine
from engine.nlp.donor_search import DonorSearchEngine
from engine.nlp.historical_morphology import HistoricalMorphologyAnalyzer
from engine.nlp.iterative_hypothesis_engine import IterativeHypothesisEngine
from engine.nlp.iterative_hypothesis_prover import IterativeHypothesisProver
from engine.nlp.loanword_classifier import LoanwordClassifier
from engine.nlp.loanword_detector import LoanwordDetector
from engine.nlp.reconstruction import ProtoTurkicReconstructor
from engine.nlp.sound_law_induction import SoundLawInductionEngine
from engine.utils.cognates import get_related_cognates
from engine.utils.geo_tagger import tag_geographical_region
from engine.utils.morphology import analyze_morphology
from engine.utils.network import Diagnostics
from engine.utils.phonetic_rules import analyze_phonetic_shifts
from engine.utils.reference_resolver import extract_cross_references
from engine.utils.seed import load_seed_entries
from engine.utils.transliteration import transliterate_to_latin
from engine.utils.variant_expander import generate_dynamic_phonetic_variants


@lru_cache(maxsize=1)
def _meaning_translations() -> dict[str, str]:
    """İngilizce -> Türkçe temel anlam eşlemesi (tohum veri)."""
    return {k.lower(): v for k, v in load_seed_entries("meaning_translations.json").items()}


def translate_meaning(meaning: str) -> str:
    """
    İngilizce sözlük tanımını Türkçeleştirir.

    Eşleşme TAM KELİME sınırındadır. Eski sürüm substring araması yapıyordu:
    ``"sun"`` girdisi ``"Sunday"``, ``"consume"``, ``"sunset"`` gibi
    kelimelerde eşleşip anlamı "güneş, gün" olarak DEĞİŞTİRİYORDU.
    """
    m = (meaning or "").strip()
    if not m or m.startswith("Online"):
        return m

    m_clean = re.sub(r"\{\{.*?\}\}", "", m).strip()
    m_clean = re.sub(r"\[\[(.*?)\]\]", r"\1", m_clean).strip()

    lowered = m_clean.lower()
    for eng, tr in _meaning_translations().items():
        # Tam kelime (veya tam ifade) sınırı
        if re.search(rf"(?<![\w-]){re.escape(eng)}(?![\w-])", lowered):
            return tr

    return m_clean or meaning

logger = get_logger(__name__)


def default_fetchers() -> list[BaseFetcher]:
    """Üretimde kullanılan varsayılan veri toplayıcı portföyü."""
    return [
        AcademicTurkologyFetcher(),
        HistoricalModernLexiconFetcher(),
        IsamAnsiklopediFetcher(),
        ArchiveOrgFetcher(),
        OsmanlicaLugatFetcher(),
        TurkicNationalDictionariesFetcher(),
        LoanwordDonorEtymologyFetcher(),
        LocalPdfBooksFetcher(),
        TietzeAltaicaFetcher(),
        EtimolojiTurkceFetcher(),
        StarlingFetcher(),
        NisanyanFetcher(),
        TdkFetcher(),
        TdkTaramaFetcher(),
        TdkDerlemeFetcher(),
        WiktionaryFetcher(),
        MultiLangWiktionaryFetcher(),
        WiktextractFetcher(),
    ]


class SearchEngine:
    def __init__(
        self,
        db_manager: DatabaseManager | None = None,
        fetchers: list[BaseFetcher] | None = None,
    ):
        """
        :param db_manager: Kalıcılık katmanı; verilmezse varsayılan SQLite yöneticisi.
        :param fetchers: Veri toplayıcı listesi. Testlerde sahte (fake) toplayıcı
            enjekte etmek için kullanılır; verilmezse üretim portföyü kurulur.
        """
        self.db = db_manager or DatabaseManager()
        self.graph_db = GraphDatabaseManager()
        self.qwen_agent = QwenEtymologyAgent()

        # NLP & İleri Hesaplamalı Modüller
        self.loanword_classifier = LoanwordClassifier()
        self.cognate_alignment_engine = CognateAlignmentEngine()
        self.reconstructor = ProtoTurkicReconstructor()
        self.donor_search_engine = DonorSearchEngine()
        self.hypothesis_engine = IterativeHypothesisEngine()
        self.hypothesis_prover = IterativeHypothesisProver()
        self.lingpy_aligner = CldfLingPyAligner()
        self.semantic_engine = DiachronicSemanticEngine()
        self.sound_law_induction = SoundLawInductionEngine()
        # Alıntı keşfi, akraba kümeleme ve tarihsel morfoloji katmanları
        self.loanword_detector = LoanwordDetector(classifier=self.loanword_classifier)
        self.cognate_cluster_engine = CognateClusterEngine()
        self.historical_morphology = HistoricalMorphologyAnalyzer()
        self.derivation_builder = DerivationNetworkBuilder()

        self.fetchers: list[BaseFetcher] = fetchers if fetchers is not None else default_fetchers()


    def search(self, query: str, save_to_db: bool = True, use_qwen_agent: bool = False) -> dict[str, Any]:
        word_clean = query.strip().lower()[: config.MAX_QUERY_LENGTH]
        search_started = time.perf_counter()
        diagnostics = Diagnostics()
        # Kaynak bazlı teşhis: hangi fetcher ne kadar sürdü, ne döndürdü, neden düştü.
        source_diagnostics: dict[str, dict[str, Any]] = {}
        stage_timings: dict[str, int] = {}

        stage_start = time.perf_counter()
        stem, suffixes = analyze_morphology(word_clean)

        # Varyant patlamasını sınırla: her varyant 21 fetcher'a ayrı istek demek.
        all_variants = list(dict.fromkeys([word_clean, stem, *generate_dynamic_phonetic_variants(word_clean)]))
        search_variants = all_variants[: config.MAX_VARIANTS]
        if len(all_variants) > len(search_variants):
            logger.info(
                "Varyant sayısı %d -> %d olarak sınırlandı (MAX_VARIANTS)",
                len(all_variants), len(search_variants),
            )
        stage_timings["morphology"] = int((time.perf_counter() - stage_start) * 1000)

        if config.CACHE_ENABLED and not use_qwen_agent:
            cached = self.db.get_finding(word_clean, max_age_seconds=config.CACHE_TTL_SECONDS)
            if cached:
                cached["from_cache"] = True
                logger.info("Önbellekten döndürüldü: %r", word_clean)
                return cached

        proto_root = ""
        root_meaning = ""
        sources = []
        turkic_entries_map = {}
        raw_fetcher_results: list[dict[str, Any]] = []

        def fetch_worker(fetcher: BaseFetcher):
            results = []
            started = time.perf_counter()
            errors: list[str] = []
            for var in search_variants:
                try:
                    res = fetcher.fetch(var)
                except Exception as exc:  # fetcher sözleşmesi istisna atmamalı; atarsa görünür olsun
                    logger.warning(
                        "Fetcher istisna attı: %s (varyant=%r)", fetcher.source_name, var, exc_info=True
                    )
                    errors.append(f"{type(exc).__name__}: {exc}")
                    continue
                if res and (res.get("turkic_languages") or res.get("proto_turkic")):
                    results.append(res)
            elapsed = int((time.perf_counter() - started) * 1000)
            return fetcher, results, elapsed, errors

        stage_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
            future_to_fetcher = {executor.submit(fetch_worker, f): f for f in self.fetchers}
            for future in concurrent.futures.as_completed(future_to_fetcher):
                fetcher = future_to_fetcher[future]
                try:
                    _fetcher_obj, results, elapsed_ms, errors = future.result()
                    source_diagnostics[fetcher.source_name] = {
                        "status": "ok" if results else ("error" if errors else "empty"),
                        "duration_ms": elapsed_ms,
                        "result_count": len(results),
                        "errors": errors or None,
                    }
                    if not results:
                        logger.debug("Kaynak veri döndürmedi: %s (%d ms)", fetcher.source_name, elapsed_ms)
                    for res in results:
                        raw_fetcher_results.append(res)
                        root_info = res.get("root", {})
                        if root_info.get("proto_turkic") and not proto_root:
                            proto_root = root_info.get("proto_turkic")
                        if root_info.get("meaning") and not root_meaning:
                            root_meaning = translate_meaning(root_info.get("meaning"))

                        for entry in res.get("turkic_languages", []):
                            entry["meaning"] = translate_meaning(entry.get("meaning", ""))
                            entry["phonetic_shift"] = analyze_phonetic_shifts(
                                word_clean, entry.get("word", ""), entry.get("lang_name", "")
                            )
                            # Kiril/Arap yazımlı biçimlerin Latin okunuşu
                            # (README'nin vaat ettiği transkripsiyon motoru;
                            #  daha önce import edilip hiç çağrılmıyordu)
                            if entry.get("script") in ("Cyrillic", "Arabic", "Runic"):
                                entry["latin_transliteration"] = transliterate_to_latin(entry.get("word", ""))
                            # Ağız kayıtlarındaki coğrafi etiket (TDK Derleme: "(Sinop)")
                            geo = tag_geographical_region(entry.get("lang_name", "") + " " + (entry.get("meaning") or ""))
                            # Yalnızca GERÇEK bir bölge tespit edildiyse ekle;
                            # "Genel Türki Coğrafya" gibi jenerik yedek etiket bilgi taşımaz.
                            if geo and geo.get("geo_coordinates"):
                                entry["geo"] = geo
                            # Sözlük tanımlarındaki "-> herkil" çapraz göndermeleri
                            refs = extract_cross_references(entry.get("meaning") or "")
                            if refs:
                                entry["cross_references"] = refs
                            key = (entry["lang_code"], entry["word"])
                            if key not in turkic_entries_map:
                                turkic_entries_map[key] = entry
                            elif turkic_entries_map[key].get("meaning") in ["", f"Online {TURKIC_LANGUAGES_MAP.get(entry['lang_code'], '')} Sözlük kaydı"]:
                                if entry.get("meaning") and not entry.get("meaning").startswith("Online"):
                                    turkic_entries_map[key] = entry

                        if res.get("turkic_languages") or root_info.get("proto_turkic"):
                            sources.append(fetcher.source_name)
                except Exception as exc:
                    logger.warning("Fetcher sonucu işlenemedi: %s", fetcher.source_name, exc_info=True)
                    source_diagnostics[fetcher.source_name] = {
                        "status": "error",
                        "duration_ms": 0,
                        "result_count": 0,
                        "errors": [f"{type(exc).__name__}: {exc}"],
                    }
        stage_timings["fetch"] = int((time.perf_counter() - stage_start) * 1000)

        sorted_entries = sorted(
            list(turkic_entries_map.values()),
            key=lambda x: (0 if x["lang_code"] == "otk" else (0.3 if x["lang_code"] == "ai" else (0.5 if x["lang_code"] == "donor" else 1)), x["lang_name"])
        )

        # 4. KÖKEN NLP VE OTONOM İNATÇI HİPOTEZ REKONSTRÜKSİYONU
        # Eğer kök anlamı henüz atanmadıysa sorted_entries içindeki gerçek sözlük tanımından çek
        if not root_meaning or root_meaning == word_clean:
            for entry in sorted_entries:
                m = entry.get("meaning", "").strip()
                if m and not m.startswith("Online") and m != word_clean:
                    root_meaning = m
                    break

        stage_start = time.perf_counter()

        # Katman 2 (çapraz lehçe yayılımı) önce hesaplanır; Katman 1'e girdi olur.
        cognate_eval = self.cognate_alignment_engine.evaluate_cognate_distribution(word_clean, sorted_entries)
        loan_eval = self.loanword_classifier.classify(
            word_clean, spreading_ratio=cognate_eval.get("spreading_ratio")
        )
        # 4 katmanlı alıntı keşif hattı (master plan Katman 1-4)
        loanword_detection = self.loanword_detector.detect(word_clean, sorted_entries)
        # Çoklu dizi hizalama ile akraba kümeleri (plan §2.1'in asıl hedefi)
        cognate_clusters = self.cognate_cluster_engine.cluster(sorted_entries)
        # Tarihsel yapım eki ağacı (plan §2.5)
        historical_morphology = self.historical_morphology.build_tree(word_clean)
        reconstruction_eval = self.reconstructor.reconstruct_proto_form(word_clean, sorted_entries)
        donor_eval = self.donor_search_engine.search_donor_neighbors(word_clean)

        finding_temp = {"root": {"proto_turkic": proto_root, "meaning": root_meaning}}
        # Hipotez motorlarına GERÇEK akraba kayıtları ve ham fetcher çıktıları verilir;
        # eskiden bu veriler geçilmiyor, motorlar kendi ürettikleri varyantları
        # "kanıt" sayıyordu.
        proven_hypothesis_eval = self.hypothesis_engine.prove_etymological_hypothesis(
            word_clean, finding_temp, sorted_entries, raw_fetcher_results
        )
        unattested_prover_eval = self.hypothesis_prover.prove_unattested_word(word_clean, sorted_entries)

        # Sözlüklerden kök bulunamadıysa karşılaştırmalı rekonstrüksiyona başvur.
        # ÖNEMLİ: kanıt yoksa `*<kelime>` biçiminde bir kök UYDURULMAZ.
        if not proto_root or proto_root == word_clean:
            hypo_pr = unattested_prover_eval.get("proven_hypothesis")
            if hypo_pr and hypo_pr.get("origin_form"):
                proto_root = hypo_pr["origin_form"]
                if not proven_hypothesis_eval.get("hypothesis_available"):
                    proven_hypothesis_eval["proven_hypothesis"] = hypo_pr
                    proven_hypothesis_eval["hypothesis_available"] = True
            elif reconstruction_eval.get("evidence_available"):
                proto_root = reconstruction_eval.get("reconstructed_root", "")

        lingpy_eval = self.lingpy_aligner.align_sequences(proto_root or word_clean, word_clean)
        semantic_eval = self.semantic_engine.evaluate_diachronic_trajectory(root_meaning or "", root_meaning or "")

        # Gerçek ses kanunu indüksiyonu: TÜM akraba çiftleri üzerinden.
        # Eskiden tek çiftten sabit 0.95 güven skoru üretiliyordu.
        induction_pairs = [
            (proto_root or word_clean, e["word"])
            for e in sorted_entries
            if e.get("word") and e.get("lang_code") in TURKIC_LANGUAGES_MAP
        ]
        sound_law_induced = (
            self.sound_law_induction.induce_from_pairs(induction_pairs)
            if len(induction_pairs) >= 2
            else self.sound_law_induction.induce_sound_law(proto_root or word_clean, word_clean)
        )


        if donor_eval and donor_eval.get("found_match"):
            donor_lang = donor_eval.get("donor_language")
            origin_form = donor_eval.get("origin_form")
            donor_meaning = donor_eval.get("donor_meaning")
            proto_root = f"[{donor_lang}] {origin_form}"
            sources.append(f"Donör Dil Etimoloji Veritabanı ({donor_lang})")
            sorted_entries.insert(0, {
                "lang_code": "donor",
                "lang_name": f"Kaynak Dil Etimolojisi ({donor_lang})",
                "word": origin_form,
                "meaning": donor_meaning,
                "script": "Original"
            })

        _hypo = proven_hypothesis_eval.get("proven_hypothesis") or {}
        _report = _hypo.get("validation_report") or {}
        # Eskiden sabit 0.95 eşiği vardı ve pratikte hiç tetiklenmiyordu.
        # Artık A-HVP rozetine bakılır.
        if _report.get("status_code") in ("VALIDATED", "NEEDS_REVIEW") and _hypo.get("donor_language"):
            hypo = _hypo
            proto_root = hypo.get("origin_form") or proto_root
            root_meaning = hypo.get("historical_meaning", root_meaning)
            sources.append(f"Derin Komşu Diller Etimoloji Veritabanı ({hypo.get('donor_language')})")
            if not any(e.get("lang_code") == "donor" for e in sorted_entries):
                sorted_entries.insert(0, {
                    "lang_code": "donor",
                    "lang_name": f"Kaynak Dil Etimolojisi ({hypo.get('donor_language')})",
                    "word": hypo.get("origin_form"),
                    "meaning": hypo.get("proof_summary"),
                    "script": "Original"
                })

        timeline = []
        for entry in sorted_entries:
            lname = entry.get("lang_name", "")
            if "Divanü Lugati't-Türk" in lname or "1074" in lname or "Orhun" in lname or "Eski Türkçe" in lname or "İSAM" in lname:
                timeline.append(f"M.Ö. III. YY - 11. YY (Hun / Orhun / DLT / İSAM): {entry.get('word')} - {(entry.get('meaning') or '')[:60]}")
            elif "1303" in lname or "Codex Cumanicus" in lname:
                timeline.append(f"14. YY (Kıpçakça / Codex Cumanicus): {entry.get('word')}")
            elif "1901" in lname or "Kamus-ı Türkî" in lname or "13.-19." in lname or "Osmanlıca Lügat" in lname:
                timeline.append(f"19. YY (Osmanlıca / Lehçe-i Osmanî / Kamus-ı Türkî): {entry.get('word')}")

        stage_timings["nlp"] = int((time.perf_counter() - stage_start) * 1000)

        morphology_info = f"Kök: {stem} + Ekler: {', '.join(suffixes)}" if suffixes else "Yalın Kök"
        related_cognates = get_related_cognates(word_clean, sorted_entries)

        # 5. Neo4j Uyumlu Graf Veritabanı Düğüm Şeması Oluşturma
        graph_export = self.graph_db.build_etymology_graph(
            word=word_clean,
            root_form=proto_root or word_clean,
            hypothesis=proven_hypothesis_eval.get("proven_hypothesis", {}),
            attestations=timeline,
            cognates=related_cognates
        )

        finding = {
            "query_word": word_clean,
            "morphology": morphology_info,
            "turkic_languages": sorted_entries,
            "root": {
                "proto_turkic": proto_root or word_clean,
                "meaning": root_meaning or word_clean,
                "reconstruction_notes": reconstruction_eval.get("reconstruction_notes", "")
            },
            "nlp_analysis": {
                "loanword_classification": loan_eval,
                "cognate_distribution": cognate_eval,
                "reconstruction": reconstruction_eval,
                "donor_matching": donor_eval,
                "proven_hypothesis": proven_hypothesis_eval.get("proven_hypothesis"),
                "unattested_word_reconstruction": unattested_prover_eval,
                "lingpy_alignment": lingpy_eval,
                "diachronic_semantic_drift": semantic_eval,
                "induced_sound_laws": sound_law_induced,
                "loanword_detection": loanword_detection,
                "cognate_clusters": cognate_clusters,
                "historical_morphology": historical_morphology,
            },
            "graph_database": graph_export,
            "timeline": list(dict.fromkeys(timeline)),
            "related_cognates": related_cognates,
            "sources": sorted(set(sources)),
            "from_cache": False,
        }

        if use_qwen_agent:
            stage_start = time.perf_counter()
            finding = self.qwen_agent.research_and_enrich(word_clean, finding)
            stage_timings["ai_enrichment"] = int((time.perf_counter() - stage_start) * 1000)

        # Gerçek telemetri: web panelindeki sahte setTimeout simülasyonunun yerini alır.
        stage_timings["total"] = int((time.perf_counter() - search_started) * 1000)
        finding["diagnostics"] = {
            "stage_timings_ms": stage_timings,
            "sources": source_diagnostics,
            "http": diagnostics.summary(),
            "variants_used": search_variants,
            "live_source_count": sum(1 for d in source_diagnostics.values() if d["status"] == "ok"),
        }
        logger.info(
            "Arama tamamlandı: %r — %d ms, %d/%d kaynak veri döndürdü",
            word_clean, stage_timings["total"],
            finding["diagnostics"]["live_source_count"], len(self.fetchers),
        )

        if save_to_db:
            self.db.save_finding(finding)

        return finding
