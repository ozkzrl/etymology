"""
Akraba Kümesi Tespiti (Cognate Cluster Detection)

Rekonstrüksiyon mimarisinin asıl hedeflerinden biri:

    "25 Türki dildeki kelimeleri ses dizilimi olarak hizalayarak gizli
     akrabalıkları (*cognate clusters*) tespit etme."

Önceki durumda ``align_sequences`` yalnızca TEK çift için, yalnızca bir kez
çağrılıyordu (``search_engine.py``: proto kök ↔ sorgu kelimesi). Diller
arası çoklu hizalama ve kümeleme hiç yoktu.

Yöntem
------
1. Tüm biçimler ikişerli hizalanır (fonetik benzerlik matrisi)
2. Eşiğin üzerindeki benzerlikler bir grafın kenarları olur
3. Bağlantılı bileşenler (connected components) akraba kümelerini verir
4. Her küme için ata biçim ve kol dağılımı raporlanır

Bu, LingPy'nin ``LexStat``/``Partial`` kümeleme yaklaşımının hafif bir
uyarlamasıdır; harici veri kümesi gerektirmez.
"""
from __future__ import annotations

from typing import Any

from engine.fetchers.base import TURKIC_LANGUAGES_MAP
from engine.logging_setup import get_logger
from engine.nlp.cldf_lingpy_aligner import CldfLingPyAligner
from engine.nlp.comparative_reconstruction import LANGUAGE_BRANCHES
from engine.utils.orthography import to_comparison_form

logger = get_logger(__name__)

#: Bu benzerliğin üzerindeki çiftler aynı akraba kümesine bağlanır.
COGNATE_THRESHOLD = 0.62


class CognateClusterEngine:
    """Türki dil biçimlerini akraba kümelerine ayırır."""

    def __init__(self, aligner: CldfLingPyAligner | None = None, threshold: float | None = None):
        self.aligner = aligner or CldfLingPyAligner()
        self.threshold = COGNATE_THRESHOLD if threshold is None else threshold

    def cluster(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Verilen dil kayıtlarını akraba kümelerine ayırır.

        :param entries: ``{"lang_code": ..., "word": ...}`` kayıtları.
        :returns: Kümeler, benzerlik matrisi ve kapsam bilgisi.
        """
        forms: list[tuple[str, str, str]] = []  # (lang_code, orijinal, karşılaştırma)
        seen: set[tuple[str, str]] = set()
        for e in entries or []:
            code = e.get("lang_code")
            if code not in TURKIC_LANGUAGES_MAP:
                continue
            raw = (e.get("word") or "").strip()
            cmp_form = to_comparison_form(raw)
            if not cmp_form or len(cmp_form) < 2:
                continue
            key = (code, cmp_form)
            if key in seen:
                continue
            seen.add(key)
            forms.append((code, raw, cmp_form))

        if len(forms) < 2:
            return {
                "evidence_available": False,
                "form_count": len(forms),
                "clusters": [],
                "reason": "Kümeleme için en az 2 farklı biçim gerekir.",
            }

        # 1. İkişerli benzerlik matrisi
        n = len(forms)
        similarity: dict[tuple[int, int], float] = {}
        for i in range(n):
            for j in range(i + 1, n):
                res = self.aligner.align_sequences(forms[i][2], forms[j][2])
                sim = res.get("phonetic_similarity")
                similarity[(i, j)] = float(sim) if sim is not None else 0.0

        # 2. Eşik üstü kenarlarla birleştirme (union-find)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

        for (i, j), sim in similarity.items():
            if sim >= self.threshold:
                union(i, j)

        # 3. Bileşenleri kümeye çevir
        groups: dict[int, list[int]] = {}
        for idx in range(n):
            groups.setdefault(find(idx), []).append(idx)

        clusters = []
        for members in sorted(groups.values(), key=len, reverse=True):
            langs = sorted({forms[i][0] for i in members})
            branches = sorted({LANGUAGE_BRANCHES.get(c) for c in langs if LANGUAGE_BRANCHES.get(c)})
            internal = [
                similarity[(min(a, b), max(a, b))]
                for ai, a in enumerate(members)
                for b in members[ai + 1:]
            ]
            clusters.append({
                "languages": langs,
                "forms": [{"lang_code": forms[i][0], "word": forms[i][1]} for i in members],
                "size": len(members),
                "branches": branches,
                "branch_count": len(branches),
                "mean_internal_similarity": round(sum(internal) / len(internal), 3) if internal else 1.0,
                "is_core_cognate_set": len(branches) >= 3,
            })

        logger.debug("Akraba kümeleme: %d biçim -> %d küme", n, len(clusters))
        return {
            "evidence_available": True,
            "form_count": n,
            "threshold": self.threshold,
            "cluster_count": len(clusters),
            "clusters": clusters,
            "largest_cluster_size": clusters[0]["size"] if clusters else 0,
            "outliers": [c for c in clusters if c["size"] == 1],
        }
