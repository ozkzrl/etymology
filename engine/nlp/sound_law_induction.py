"""
Ses Kanunu İndüksiyon Motoru (Sound Law Induction)

Akraba kelime çiftlerinden düzenli ses dönüşüm kurallarını çıkarır.

Düzeltilen sorun
----------------
* Güven skoru sabitti: kural üretildiyse ``0.95``, üretilmediyse ``0.70``.
  Herhangi bir ünlü farkı VOWEL_SHIFT kuralını tetiklediği için pratikte
  neredeyse her çift ``0.95`` alıyordu.
* Tek çiftten "indüksiyon" yapılamaz. Gerçek indüksiyon, aynı kuralın BİRDEN
  ÇOK çiftte tekrarlanmasıyla doğrulanır. ``induce_from_pairs`` bunu yapar;
  tek çift için ``rule_confidence`` artık ``None`` (kanıt yok) döner.
"""

from collections import Counter
from typing import Any

from engine.utils.orthography import to_comparison_form


class SoundLawInductionEngine:
    """Akraba ve ata sözcük çiftlerinden ses yasası kurallarını indükleyen motor"""

    def induce_sound_law(self, source_word: str, target_word: str) -> dict[str, Any]:
        s = to_comparison_form(source_word or "")
        t = to_comparison_form(target_word or "")

        if not s or not t or s == t:
            return {
                "source_word": s,
                "target_word": t,
                "has_induced_rule": False,
                "induced_rules": [],
                "rule_confidence": 1.0
            }

        induced_rules = []

        # 1. Söz Başı Dönüşümleri (Initial Consonant Shifts)
        if s[0] != t[0]:
            rule_id = f"INITIAL_{s[0].upper()}_{t[0].upper()}"
            induced_rules.append({
                "rule_id": rule_id,
                "pattern": f"#{s[0]} -> #{t[0]}",
                "position": "initial",
                "description": f"Söz başı {s[0]}- ünsüzünün {t[0]}- ünsüzüne dönüşmesi"
            })

        # 2. Söz Sonu Dönüşümleri (Final Shifts)
        if s[-1] != t[-1]:
            rule_id = f"FINAL_{s[-1].upper()}_{t[-1].upper()}"
            induced_rules.append({
                "rule_id": rule_id,
                "pattern": f"{s[-1]}# -> {t[-1]}#",
                "position": "final",
                "description": f"Söz sonu -{s[-1]} ünsüzünün -{t[-1]} sesine dönüşmesi"
            })

        # 3. İç Ses ve Ünlü Uyumu Kaymaları
        s_vowels = [c for c in s if c in 'aeıioöuü']
        t_vowels = [c for c in t if c in 'aeıioöuü']
        if s_vowels and t_vowels and s_vowels != t_vowels:
            induced_rules.append({
                "rule_id": "VOWEL_SHIFT",
                "pattern": f"{''.join(s_vowels)} -> {''.join(t_vowels)}",
                "position": "medial",
                "description": f"Kök ünlü kümesinin {''.join(s_vowels)} -> {''.join(t_vowels)} şeklinde kayması"
            })

        return {
            "source_word": s,
            "target_word": t,
            "has_induced_rule": len(induced_rules) > 0,
            "induced_rules": induced_rules,
            # Tek çiftten güven skoru ÇIKARILAMAZ. İndüksiyon, kuralın birden
            # çok çiftte tekrarlanmasını gerektirir -> `induce_from_pairs`.
            "rule_confidence": None,
            "evidence_available": False,
            "note": "Tek çiftlik gözlem; kural güveni için induce_from_pairs kullanın.",
        }

    def induce_from_pairs(self, pairs: list[tuple[str, str]]) -> dict[str, Any]:
        """
        Birden çok akraba çiftinden ses kanunu indükler.

        Bir kuralın güveni, o kuralın kaç çiftte gözlendiğine ve kuralın
        uygulanabilir olduğu çiftlerin ne kadarında GERÇEKTEN gözlendiğine
        bağlıdır (düzenlilik oranı).

        :param pairs: ``(ata_biçim, modern_biçim)`` çiftleri.
        """
        if len(pairs) < 2:
            return {
                "pair_count": len(pairs),
                "evidence_available": False,
                "induced_rules": [],
                "note": "İndüksiyon için en az 2 akraba çifti gerekir.",
            }

        observations: list[dict[str, Any]] = []
        for src, tgt in pairs:
            res = self.induce_sound_law(src, tgt)
            observations.extend(res.get("induced_rules", []))

        counts = Counter((r["rule_id"], r["pattern"]) for r in observations)
        by_id: dict[str, list[dict[str, Any]]] = {}
        for rule in observations:
            by_id.setdefault(rule["rule_id"], []).append(rule)

        induced = []
        for (rule_id, pattern), count in counts.most_common():
            # Düzenlilik: bu kural, aynı türden kuralların kaçında bu desenle gözlendi?
            same_kind = len(by_id.get(rule_id, []))
            regularity = count / same_kind if same_kind else 0.0
            support = count / len(pairs)
            confidence = round(0.6 * support + 0.4 * regularity, 3)
            sample = next(r for r in observations if r["rule_id"] == rule_id and r["pattern"] == pattern)
            induced.append({
                **sample,
                "observed_in_pairs": count,
                "total_pairs": len(pairs),
                "support": round(support, 3),
                "regularity": round(regularity, 3),
                "confidence": confidence,
            })

        return {
            "pair_count": len(pairs),
            "evidence_available": True,
            "induced_rules": induced,
            "note": "Güven = 0.6 × destek (kaç çiftte gözlendi) + 0.4 × düzenlilik.",
        }
