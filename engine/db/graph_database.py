"""
Neo4j Graf Veritabanı ve Çizge Düğüm Şeması Yöneticisi (Graph Database & Visualizer Manager)
Etimoloji vakalarını Neo4j düğüm ve kenar yapısında (WordForm, EtymologyCase, SoundLaw, Attestation)
modeller ve Cytoscape.js / React Flow ile uyumlu JSON formatında dışa aktarır.
"""

import re
from typing import Any


def _node_id(prefix: str, value: str) -> str:
    """
    Cytoscape/Neo4j için güvenli düğüm kimliği üretir.

    Kelime boşluk veya özel karakter içerdiğinde eski kimlikler bozuk
    seçici (selector) üretiyor ve çakışabiliyordu.
    """
    slug = re.sub(r"[^0-9a-zçğıöşüA-ZÇĞİÖŞÜ_-]+", "_", (value or "").strip().lower()) or "x"
    return f"{prefix}_{slug}"


class GraphDatabaseManager:
    """Neo4j Uyumlu Graf Düğüm Şeması ve Görsel Çizge Üreticisi"""

    def build_etymology_graph(self, word: str, root_form: str, hypothesis: dict[str, Any], attestations: list[str], cognates: list[str]) -> dict[str, Any]:
        nodes = []
        edges = []

        w_clean = word.strip().lower()
        r_clean = (root_form or w_clean).strip().lstrip("*")
        # Kanıt yoksa hipotez üretilmez ve None gelir; graf yine kurulmalıdır.
        hypothesis = hypothesis or {}

        # 1. Düğüm: Ana Kelime (WordForm Target Node)
        target_node_id = _node_id("word", w_clean)
        nodes.append({
            "id": target_node_id,
            "label": w_clean,
            "type": "WordForm",
            "category": "TargetWord",
            "properties": {"word": w_clean, "lang": "tr"}
        })

        # 2. Düğüm: Ata Kök (WordForm Proto Node)
        proto_node_id = _node_id("proto", r_clean)
        nodes.append({
            "id": proto_node_id,
            "label": f"*{r_clean}",
            "type": "WordForm",
            "category": "ProtoRoot",
            "properties": {"word": f"*{r_clean}", "lang": hypothesis.get("donor_language", "Proto-Türkçe")}
        })

        # Kenar: Ata Kök -> Hedef Kelime (DERIVED_FROM)
        edges.append({
            "id": f"edge_{proto_node_id}_{target_node_id}",
            "source": proto_node_id,
            "target": target_node_id,
            "relationship": "DERIVED_FROM",
            "label": "türetildi"
        })

        # 3. Düğüm: Etimoloji Vakası (EtymologyCase Node)
        case_node_id = _node_id("case", w_clean)
        nodes.append({
            "id": case_node_id,
            "label": f"Vaka: {hypothesis.get('hypothesis_type', 'Etimoloji Hipotezi')[:25]}",
            "type": "EtymologyCase",
            "properties": {
                # Kanıt yoksa None yazılır; eskiden varsayılan 0.90 güven skoru
                # graf düğümüne uydurma olarak işleniyordu.
                "confidence_score": hypothesis.get("confidence_score"),
                "donor_language": hypothesis.get("donor_language", "Proto-Türkçe")
            }
        })
        edges.append({
            "id": f"edge_{target_node_id}_{case_node_id}",
            "source": target_node_id,
            "target": case_node_id,
            "relationship": "HAS_CASE",
            "label": "vaka kaydı"
        })

        # 4. Düğümler: Yazılı Tanıklamalar (Attestation Nodes)
        for idx, att in enumerate(attestations[:4]):
            att_id = _node_id("att", f"{w_clean}_{idx}")
            nodes.append({
                "id": att_id,
                "label": att[:30],
                "type": "Attestation",
                "properties": {"record": att}
            })
            edges.append({
                "id": f"edge_{target_node_id}_{att_id}",
                "source": target_node_id,
                "target": att_id,
                "relationship": "ATTESTED_IN",
                "label": "tanıklandı"
            })

        # 5. Düğümler: Akraba Biçimler (Cognate Nodes)
        for idx, cog in enumerate(cognates[:5]):
            cog_id = _node_id("cog", f"{w_clean}_{idx}")
            nodes.append({
                "id": cog_id,
                "label": cog,
                "type": "WordForm",
                "category": "Cognate",
                "properties": {"word": cog}
            })
            edges.append({
                "id": f"edge_{proto_node_id}_{cog_id}",
                "source": proto_node_id,
                "target": cog_id,
                "relationship": "COGNATE_OF",
                "label": "akraba biçim"
            })

        return {
            "query_word": w_clean,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "graph_data": {
                "nodes": nodes,
                "edges": edges
            },
            "cytoscape_format": {
                "elements": [
                    {"data": n} for n in nodes
                ] + [
                    {"data": e} for e in edges
                ]
            }
        }
