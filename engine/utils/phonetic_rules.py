"""
Fonetik Ses Kayması ve Dilbilimsel Dönüşüm Analizcisi (Phonetic Shift & Sound Law Detector)
Türkiye Türkçesindeki kelime ile Türki dillerdeki akraba kelimeler ve kök diller arasındaki ses dönüşüm kurallarını denetler.
"""
import re
from difflib import SequenceMatcher
from typing import Any

from engine.utils.orthography import to_comparison_form, to_expected_reflex

#: Bu değerin altındaki sıralı benzerlik, tanımlı kural da yoksa "kırık zincir" sayılır.
BROKEN_CHAIN_THRESHOLD = 0.34
#: Tanımlı bir ses kanunu eşleştiğinde skora eklenen pay.
RULE_BONUS = 0.15


def _one_way_match(src_pat: str, tgt_pat: str, source: str, target: str) -> bool:
    """Kaynak deseni kaynakta, hedef deseni hedefte AYNI konumda eşleşiyor mu?"""
    ms = re.search(src_pat, source)
    mt = re.search(tgt_pat, target)
    if not ms or not mt:
        return False
    if src_pat.startswith("^") or tgt_pat.startswith("^"):
        return ms.start() == 0 and mt.start() == 0
    if src_pat.endswith("$") or tgt_pat.endswith("$"):
        return ms.end() == len(source) and mt.end() == len(target)
    return True


def _rule_applies(rule: dict[str, Any], source: str, target: str) -> bool:
    """
    Kural bu kelime çiftine uyuyor mu?

    Ses kanunları SİMETRİK denkliklerdir: ``g- ~ k-`` kuralı hem ``gök -> kök``
    hem ``köŕ -> göz`` yönünde geçerlidir. Bu yüzden her iki yön de denenir.

    Ancak desenler yine KONUM duyarlıdır — eski uygulama iki deseni bağımsız
    arıyor, hangi sesin neye dönüştüğüne bakmıyordu; bu yüzden 'gel' -> 'kul'
    de 'gök' -> 'kök' kadar geçerli sayılıyordu.
    """
    src_pat, tgt_pat = rule["source_pattern"], rule["target_pattern"]
    return _one_way_match(src_pat, tgt_pat, source, target) or _one_way_match(
        tgt_pat, src_pat, source, target
    )

# Tanımlı Geçerli Ses Kanunları ve Dönüşüm Kuralları
RECOGNIZED_SOUND_LAWS = [
    {
        "id": "OGUZ_KIPCAK_INITIAL_G_K",
        "name": "Oğuz - Kıpçak/Sibirya Söz Başı Ötümlüleşme/Ötümsüzleşme (g- ~ k-)",
        "source_pattern": r"^g",
        "target_pattern": r"^[kк]",
        "valid": True,
        "description": "Baştaki ötümlü 'g-' konsonantının ötümsüz 'k-' sesine dönüşmesi"
    },
    {
        "id": "INITIAL_D_T",
        "name": "Söz Başı Sertleşme (d- ~ t-)",
        "source_pattern": r"^d",
        "target_pattern": r"^[tт]",
        "valid": True,
        "description": "Baştaki ötümlü 'd-' sesinin 't-' biçimine sertleşmesi"
    },
    {
        "id": "INITIAL_B_M",
        "name": "Söz Başı Genizsilleşme (b- ~ m-)",
        "source_pattern": r"^b",
        "target_pattern": r"^[mм]",
        "valid": True,
        "description": "Baştaki 'b-' ünsüzünün genizsilleşerek 'm-' sesine dönüşmesi (ben -> men)"
    },
    {
        "id": "FINAL_Z_S_R",
        "name": "Proto-Türkçe r-z / z-s Sızıcılaşma Denkliği (-z ~ -s ~ -r)",
        "source_pattern": r"[zŕ]$",
        "target_pattern": r"[sсҫśrрŕ]$",
        "valid": True,
        "description": "Sondaki '-z' ünsüzünün sızıcı '-s / -ś' veya Lir-Şaz kolunda '-r' sesine dönüşmesi"
    },
    {
        "id": "OGUR_INITIAL_S_SH",
        "name": "Oğur/Çuvaş Söz Başı Sızıcılaşma (s- ~ ş-)",
        "source_pattern": r"^s",
        "target_pattern": r"^[шš]",
        "valid": True,
        "description": "Oğur/Çuvaş koluna özgü baştaki 's-' ünsüzünün 'ş-' (š-) sesine kayması"
    },
    {
        "id": "INTERVOCALIC_G_G_V_W",
        "name": "Ünlü Arası ve Son Ötümlüleşme/Düşme (g ~ ğ ~ v ~ w)",
        "source_pattern": r"[gğ]",
        "target_pattern": r"[vwву]",
        "valid": True,
        "description": "Orta/son 'g/ğ' sesinin 'v/w' sesine yumuşaması (sub ~ suv ~ su)"
    },
    {
        "id": "INITIAL_Y_J_C_ZH",
        "name": "Söz Başı Akıcı Y- Değişimi (y- ~ j- ~ c- ~ zh-)",
        "source_pattern": r"^y",
        "target_pattern": r"^[jcç]|^[жҗ]",
        "valid": True,
        "description": "Kazakça/Kırgızca/Altayca söz başı 'y-' ~ 'j-' ~ 'c-' diyalekt kayması"
    },
    {
        "id": "FINAL_B_V_W_DROP",
        "name": "Söz Sonu Konsonant Düşmesi (b/v/w → ∅)",
        "source_pattern": r"[bvw]$",
        "target_pattern": r"[aeiouıöüuаеіоөуүы]$",
        "valid": True,
        "description": "Söz sonundaki b/v/w ünsüzünün Türki dil kollarında düşmesi (sub > suv > su, suğ; teŋiz gibi)"
    },
    {
        "id": "FINAL_B_V_W_TO_U",
        "name": "Söz Sonu v/w/ğ → u/ü Ünlüleşmesi",
        "source_pattern": r"[vwğ]$",
        "target_pattern": r"[uü]$",
        "valid": True,
        "description": "Söz sonundaki v/w/ğ'nın ünlüleşmesi (suv > suu, suğ > su)"
    },
    {
        "id": "FRENCH_LOAN_ADAPTATION",
        "name": "Fransızca/Batı Dilleri Fonotaktik Uyarlaması (c-/qu-/ch-/ph-/küp -> k-/f-/s-)",
        "source_pattern": r"^(qu|ch|ph|ps|st|sp|tr|pr|kl|gr|fl|bl|cr|dr|sc|sk|sl|sm|sn)",
        "target_pattern": r"^[kçfstg]",
        "valid": True,
        "description": "Batı dillerinden geçen terimlerin (Fransızca/İtalyanca/Latince) Türkçe ses sistemine jenerik uyarlanması"
    }
]

def analyze_phonetic_shifts(source_word: str, target_word: str, lang_name: str = "") -> str:
    s = source_word.strip().lower()
    t = target_word.strip().lower()

    explanations = []
    for rule in RECOGNIZED_SOUND_LAWS:
        if re.search(rule["source_pattern"], s) and re.search(rule["target_pattern"], t):
            explanations.append(rule["name"])

    if explanations:
        return "; ".join(explanations)
    return "Standart Ses Denkliği"

def verify_phonetic_chain(source_form: str, target_form: str) -> dict[str, Any]:
    """
    Kök biçim ile hedef kelime arasında geçerli bir ses evrim zinciri var mı?

    Düzeltilen sorunlar
    -------------------
    * Benzerlik **karakter kümesi kesişimi** ile ölçülüyordu; sıra ve konum
      dikkate alınmadığı için ``kitab`` ile ``xyzabc`` %75 skor alıyor,
      ``kös`` ile ``sök`` %100 benzer çıkıyordu. Artık sıralı dizi hizalaması
      (``SequenceMatcher``) kullanılır.
    * Kural eşleşmesi iki BAĞIMSIZ regex ile yapılıyordu: kaynakta desen var mı,
      hedefte desen var mı. Hangi sesin neye dönüştüğü denetlenmiyordu, bu yüzden
      ``gel -> kul`` da ``gök -> kök`` kadar geçerli sayılıyordu. Artık kuralın
      kaynak deseni kaynağın, hedef deseni hedefin AYNI konumunda eşleşmelidir.
    * Skor eşiği yoksa ``0.75`` gibi cömert sabitler veriliyordu; artık skor
      doğrudan hizalama oranından türetilir ve kanıt yoksa ``evidence_available``
      ``False`` döner.
    """
    s_raw = (source_form or "").strip().lower().lstrip("*")
    t_raw = (target_form or "").strip().lower()

    if not s_raw:
        s_raw = t_raw
    if not t_raw:
        return {
            "is_valid": None,
            "score": None,
            "evidence_available": False,
            "violations": [],
            "matched_rules": [],
            "reason": "Karşılaştırılacak hedef biçim yok.",
        }

    if s_raw == t_raw:
        return {
            "is_valid": True,
            "score": 1.0,
            "evidence_available": True,
            "violations": [],
            "matched_rules": ["Birebir ses eşleşmesi"],
            "similarity": 1.0,
        }

    matched_rules = [r["name"] for r in RECOGNIZED_SOUND_LAWS if _rule_applies(r, s_raw, t_raw)]

    # Diller arası karşılaştırma: Kiril/özel işaretler ortak Latin biçimine
    # indirgenir; ata biçimdeki rekonstrüksiyon sesleri (ŕ, ĺ, ŋ, j) Ortak
    # Türkçe'de BEKLENEN reflekslerine çevrilir. Aksi hâlde *köŕ ~ göz gibi
    # düzenli bir denklik "fark" sayılıp benzerliği haksız yere düşürür.
    s_cmp = to_expected_reflex(s_raw)
    t_cmp = to_comparison_form(t_raw)

    if not s_cmp or not t_cmp:
        return {
            "is_valid": None,
            "score": None,
            "evidence_available": False,
            "violations": [],
            "matched_rules": matched_rules,
            "reason": "Biçimler karşılaştırılabilir bir yazı sistemine indirgenemedi.",
        }

    # SIRALI benzerlik: karakter kümesi değil, dizi hizalaması.
    similarity = round(SequenceMatcher(None, s_cmp, t_cmp).ratio(), 3)

    violations = []
    if not matched_rules and similarity < BROKEN_CHAIN_THRESHOLD:
        violations.append(
            f"'{s_raw}' ile '{t_raw}' arasında tanımlı bir ses kanunu yok ve "
            f"dizi benzerliği çok düşük ({similarity}) — fonetik halka kırık."
        )

    is_valid = not violations
    # Skor doğrudan kanıttan türetilir: sıralı benzerlik, tanımlı kural varsa ödüllendirilir.
    score = similarity
    if matched_rules:
        score = min(1.0, similarity + RULE_BONUS)
    score = round(score, 3)

    return {
        "is_valid": is_valid,
        "score": score,
        "evidence_available": True,
        "similarity": similarity,
        "violations": violations,
        "matched_rules": matched_rules or ["Tanımlı kural yok (yalnızca dizi benzerliği)"],
    }
