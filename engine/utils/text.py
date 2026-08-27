"""
Ortak Metin Yardımcıları (Shared Text Helpers)

``re.sub(r'<[^>]+>', ...)`` deseni projede **14 ayrı yerde** tekrarlanıyordu;
her biri farklı boşluk/varlık işleme davranışına sahipti.
"""
from __future__ import annotations

import html as _html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_WS_RE = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    """HTML etiketlerini siler, varlıkları çözer, boşlukları normalize eder."""
    if not text:
        return ""
    t = _SCRIPT_STYLE_RE.sub(" ", text)
    t = _COMMENT_RE.sub(" ", t)
    t = _TAG_RE.sub(" ", t)
    t = _html.unescape(t)
    return _WS_RE.sub(" ", t).strip()


def truncate(text: str | None, limit: int, suffix: str = "…") -> str:
    """Metni sınıra kırpar; kırpıldıysa sonuna ek koyar."""
    t = (text or "").strip()
    return t if len(t) <= limit else t[: max(0, limit - len(suffix))] + suffix
