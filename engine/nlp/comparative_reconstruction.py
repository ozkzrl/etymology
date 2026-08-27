"""
Karşılaştırmalı Yöntemle Proto-Türkçe Rekonstrüksiyon (Comparative Reconstruction)

Tarihsel dilbilimin karşılaştırmalı yöntemini uygular: akraba biçimler hizalanır,
her konum için bir **denklik kümesi** (correspondence set) çıkarılır ve bilinen
Proto-Türkçe ses denkliklerine göre ata sesi seçilir.

Neden yeniden yazıldı
---------------------
Önceki iki modül birbiriyle ÇELİŞİYORDU ve ikisi de aynı aramada çalışıyordu:

* ``reconstruction.py``          : ``d-`` -> ``t-``  (ileri yön)
* ``predictive_reconstructor.py``: ``t-`` -> ``d-``  (ters yön)

Ayrıca ikisi de akraba verisini kullanmıyordu: ``reconstruct_proto_form``
imzasında ``turkic_entries`` parametresi vardı ama gövdede hiç okunmuyordu;
``predictive_reconstructor`` ise akraba listesini yalnızca ``len()`` almak için
kullanıp içeriği atıyordu. Güven skorları sabitti (0.88 / 0.75).

Artık ata biçim gerçekten akraba biçimlerden türetilir ve güven skoru kanıttan
(kaç dil, kaç ayrı Türki kol, hizalama tutarlılığı) hesaplanır.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from engine.fetchers.base import TURKIC_LANGUAGES_MAP
from engine.logging_setup import get_logger
from engine.utils.orthography import to_comparison_form

logger = get_logger(__name__)

#: Türki dillerin kolları. Kol çeşitliliği rekonstrüksiyon güvenini belirler:
#: yalnızca Oğuz kolundan gelen kanıt, Oğur (Çuvaş) kolundan da desteklenen
#: kanıttan çok daha zayıftır.
LANGUAGE_BRANCHES: dict[str, str] = {
    "tr": "oguz", "az": "oguz", "tk": "oguz", "gag": "oguz", "ota": "oguz",
    "kk": "kipchak", "ky": "kipchak", "tt": "kipchak", "ba": "kipchak",
    "kaa": "kipchak", "nog": "kipchak", "kum": "kipchak", "krc": "kipchak",
    "crh": "kipchak",
    "uz": "karluk", "ug": "karluk", "chg": "karluk", "slq": "karluk",
    "sah": "siberian", "tyv": "siberian", "alt": "siberian",
    "khk": "siberian", "cjs": "siberian",
    "cv": "oghur",
    "otk": "old_turkic",
}

#: Bilinen Proto-Türkçe denklik kümeleri.
#: Her giriş: (sesler, ata_ses, açıklama, konum).
#: Konum: "initial" (söz başı), "final" (söz sonu), "any" (her yer).
#: Bunlar Türkolojide yerleşik denkliklerdir (Lir-Şaz / rotasizm-lambdaizm).
CORRESPONDENCE_SETS: list[tuple[frozenset[str], str, str, str]] = [
    # --- Söz sonu (Lir-Şaz) ---
    (frozenset({"z", "r"}), "ŕ", "Lir-Şaz rotasizmi: Ortak Türkçe -z ~ Çuvaşça -r < Proto-Türkçe *-ŕ", "final"),
    (frozenset({"z", "r", "s"}), "ŕ", "Ortak Türkçe -z/-s ~ Çuvaşça -r < Proto-Türkçe *-ŕ", "final"),
    (frozenset({"ş", "l"}), "ĺ", "Lambdaizm: Ortak Türkçe -ş ~ Çuvaşça -l < Proto-Türkçe *-ĺ", "final"),
    (frozenset({"s", "ş", "l"}), "ĺ", "Ortak Türkçe -s/-ş ~ Çuvaşça -l < Proto-Türkçe *-ĺ", "final"),
    # --- Söz başı ---
    # Oğuz kolu söz başı ötümsüzleri ötümlüleştirdi (t->d, k->g); ata biçim ötümsüzdür.
    (frozenset({"d", "t"}), "t", "Söz başı ötümlüleşme: Oğuz d- ~ diğer t- < Proto-Türkçe *t-", "initial"),
    (frozenset({"g", "k"}), "k", "Söz başı ötümlüleşme: Oğuz g- ~ diğer k- < Proto-Türkçe *k-", "initial"),
    (frozenset({"y", "c", "j", "ç"}), "j", "Söz başı akıcı: y- ~ c- ~ j- < Proto-Türkçe *j-", "initial"),
    (frozenset({"b", "m"}), "b", "Genizsilleşme: b- ~ m- < Proto-Türkçe *b-", "initial"),
    (frozenset({"h", "k", "q"}), "k", "Söz başı h- ~ k- denkliği", "initial"),
    # --- Konumdan bağımsız ---
    (frozenset({"d", "y", "z", "t", "r"}), "d", "Klasik *d̮ denkliği: d ~ y ~ z ~ t ~ r", "any"),
    (frozenset({"b", "v", "w", "u"}), "b", "Ünsüz yumuşaması: b ~ v ~ w ~ u < Proto-Türkçe *b", "any"),
    (frozenset({"g", "ğ", "v", "w"}), "g", "Ünlü arası yumuşama: g ~ ğ ~ v ~ w < Proto-Türkçe *g", "any"),
    (frozenset({"n", "ŋ"}), "ŋ", "Genizsil denkliği: -n- ~ -ŋ- < Proto-Türkçe *-ŋ-", "any"),
]


def _pick_proto_phoneme(sounds: list[str], position: str) -> tuple[str, str | None]:
    """
    Bir konumdaki seslerden ata sesi seçer.

    Denklikler KONUMA DUYARLIDIR: söz başı ``d ~ t`` denkliği Proto-Türkçe
    ``*t-`` verirken, söz içi ``d ~ y ~ z`` denkliği ``*d̮`` verir. Konumu
    yok saymak yanlış ata biçim üretir.

    :param position: "initial" | "medial" | "final"
    :returns: (ata_ses, açıklama)
    """
    present = {s for s in sounds if s}
    if not present:
        return "", None
    if len(present) == 1:
        return next(iter(present)), None

    best: tuple[int, int, str, str] | None = None
    for members, proto, note, applies_to in CORRESPONDENCE_SETS:
        if applies_to != "any" and applies_to != position:
            continue
        overlap = present & members
        if len(overlap) >= 2:
            # Konuma özgü kural, genel kurala tercih edilir.
            specificity = 1 if applies_to == "any" else 2
            cand = (specificity, len(overlap), proto, note)
            if best is None or cand[:2] > best[:2]:
                best = cand
    if best:
        return best[2], best[3]

    return Counter(s for s in sounds if s).most_common(1)[0][0], None


class ComparativeReconstructor:
    """Akraba biçimlerden Proto-Türkçe ata biçimi türetir."""

    def __init__(self, aligner: Any | None = None):
        self._aligner = aligner

    @property
    def aligner(self) -> Any:
        if self._aligner is None:
            from engine.nlp.cldf_lingpy_aligner import CldfLingPyAligner

            self._aligner = CldfLingPyAligner()
        return self._aligner

    def reconstruct(self, word: str, turkic_entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """
        :param word: Modern sorgu kelimesi (çapa biçim).
        :param turkic_entries: Fetcher'lardan gelen gerçek akraba kayıtları.
        :returns: Ata biçim, uygulanan denklikler ve KANITA DAYALI güven skoru.
        """
        anchor = to_comparison_form(word)
        entries = [e for e in (turkic_entries or []) if e.get("lang_code") in TURKIC_LANGUAGES_MAP]

        # Dil başına tek biçim (en kısa, en çekirdek olan)
        by_lang: dict[str, str] = {}
        for e in entries:
            form = to_comparison_form(e.get("word") or "")
            if not form or len(form) < 2:
                continue
            code = e["lang_code"]
            if code not in by_lang or len(form) < len(by_lang[code]):
                by_lang[code] = form

        if not anchor:
            return {
                "word": word,
                "reconstructed_root": "",
                "is_reconstructible": False,
                "evidence_available": False,
                "confidence": None,
                "reconstruction_notes": "Kelime karşılaştırılabilir bir biçime indirgenemedi.",
            }

        if len(by_lang) < 2:
            # Karşılaştırmalı yöntem en az iki bağımsız tanık gerektirir.
            return {
                "word": word,
                "reconstructed_root": "",
                "is_reconstructible": False,
                "evidence_available": False,
                "confidence": None,
                "witness_count": len(by_lang),
                "reconstruction_notes": (
                    f"Karşılaştırmalı rekonstrüksiyon için en az 2 bağımsız dil tanığı gerekir; "
                    f"{len(by_lang)} bulundu. Ata biçim türetilemez."
                ),
            }

        # Tüm tanıkları çapa biçime hizala ve konum bazlı denklik kümeleri kur
        columns: list[list[str]] = [[] for _ in anchor]
        aligned_count = 0
        for _code, form in sorted(by_lang.items()):
            try:
                res = self.aligner.align_sequences(anchor, form)
            except Exception:
                logger.warning("Hizalama başarısız: %s ~ %s", anchor, form, exc_info=True)
                continue
            a1, a2 = res.get("aligned_seq1", ""), res.get("aligned_seq2", "")
            if not a1 or not a2:
                continue
            aligned_count += 1
            pos = 0
            for c1, c2 in zip(a1, a2, strict=False):
                if c1 == "-":
                    continue
                if pos < len(columns):
                    columns[pos].append(c2 if c2 != "-" else "")
                pos += 1

        if aligned_count < 2:
            return {
                "word": word,
                "reconstructed_root": "",
                "is_reconstructible": False,
                "evidence_available": False,
                "confidence": None,
                "reconstruction_notes": "Tanık biçimler hizalanamadı.",
            }

        proto_chars: list[str] = []
        applied_rules: list[str] = []
        agreement_scores: list[float] = []
        last_idx = len(anchor) - 1
        for i, ch in enumerate(anchor):
            sounds = [*columns[i], ch]
            position = "initial" if i == 0 else ("final" if i == last_idx else "medial")
            proto_ch, note = _pick_proto_phoneme(sounds, position)
            proto_chars.append(proto_ch or ch)
            if note and note not in applied_rules:
                applied_rules.append(note)
            # Bu konumda tanıklar ne kadar hemfikir?
            counts = Counter(s for s in sounds if s)
            agreement_scores.append(counts.most_common(1)[0][1] / len(sounds) if counts else 0.0)

        proto_form = "*" + "".join(proto_chars)

        # --- KANITA DAYALI güven skoru (eskiden sabit 0.88 / 0.75) ---
        branches = {LANGUAGE_BRANCHES.get(c) for c in by_lang if LANGUAGE_BRANCHES.get(c)}
        witness_factor = min(1.0, len(by_lang) / 6.0)          # 6+ dil tam puan
        branch_factor = min(1.0, len(branches) / 4.0)           # 4+ kol tam puan
        agreement = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 0.0
        confidence = round(0.40 * witness_factor + 0.30 * branch_factor + 0.30 * agreement, 3)

        return {
            "word": word,
            "reconstructed_root": proto_form,
            "is_reconstructible": True,
            "evidence_available": True,
            "confidence": confidence,
            "witness_count": len(by_lang),
            "witness_languages": sorted(by_lang),
            "branch_count": len(branches),
            "branches": sorted(b for b in branches if b),
            "column_agreement": round(agreement, 3),
            "applied_correspondences": applied_rules,
            "reconstruction_notes": (
                f"{len(by_lang)} dil tanığı ve {len(branches)} Türki kol üzerinden karşılaştırmalı "
                f"yöntemle türetildi: {anchor} -> {proto_form}"
            ),
        }
