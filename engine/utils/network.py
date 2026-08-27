"""
Ortak HTTP İstemcisi (Shared HTTP Client)

Projedeki TÜM dış ağ erişiminin tek kapısı. Daha önce 21 fetcher, 3 kazıyıcı ve
2 LLM araç modülü kendi `urllib.request` çağrısını, kendi User-Agent'ını ve
kendi zaman aşımını yazıyordu (32 farklı `timeout=`, 11 farklı UA); retry/backoff
mantığı bu dosyada yazılmış ama hiçbir yerden çağrılmıyordu.

Sağladıkları:
  * `requests.Session` üzerinde bağlantı havuzu
  * Üstel geri çekilmeli (exponential backoff) yeniden deneme
  * Merkezî User-Agent ve üç kademeli zaman aşımı
  * SSRF koruması: özel/loopback adres reddi, opsiyonel alan adı beyaz listesi
  * Her isteğin süresini ve sonucunu kaydeden teşhis (diagnostics) kancası
"""
from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

from engine.config import (
    HTTP_BACKOFF_BASE,
    HTTP_MAX_RETRIES,
    HTTP_TIMEOUT_MEDIUM,
    TRUSTED_DOMAINS,
    USER_AGENT,
)
from engine.logging_setup import get_logger

logger = get_logger(__name__)


class UnsafeURLError(ValueError):
    """URL güvenlik denetiminden geçemedi (SSRF koruması)."""


@dataclass
class RequestRecord:
    """Tek bir dış isteğin teşhis kaydı."""
    url: str
    status: str          # "ok" | "http_error" | "network_error" | "blocked"
    duration_ms: int
    http_status: int | None = None
    error: str | None = None


@dataclass
class Diagnostics:
    """Bir arama boyunca yapılan tüm isteklerin toplandığı kayıt defteri."""
    records: list[RequestRecord] = field(default_factory=list)

    def add(self, record: RequestRecord) -> None:
        self.records.append(record)

    @property
    def total_requests(self) -> int:
        return len(self.records)

    @property
    def total_ms(self) -> int:
        return sum(r.duration_ms for r in self.records)

    def summary(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for r in self.records:
            by_status[r.status] = by_status.get(r.status, 0) + 1
        return {
            "total_requests": self.total_requests,
            "total_ms": self.total_ms,
            "by_status": by_status,
        }


def _decode_body(resp: requests.Response) -> str:
    """
    Gövdeyi doğru karakter kodlamasıyla çözer.

    Bazı kaynaklar (ör. etimolojiturkce.com) ``Content-Type: text/html``
    başlığını charset bildirmeden gönderir; ``requests`` bu durumda RFC gereği
    ISO-8859-1 varsayar ve Türkçe karakterler mojibake olur ("eş" -> "eÅ").
    Sunucu charset bildirmediyse içerikten sezilen kodlama kullanılır.
    """
    declared = (resp.headers.get("Content-Type") or "").lower()
    if "charset=" not in declared:
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Süreç ömrü boyunca paylaşılan HTTP oturumu."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "tr,en;q=0.8",
        })
    return _session


def reset_session() -> None:
    """Testlerin oturumu sıfırlaması için."""
    global _session
    if _session is not None:
        _session.close()
    _session = None


# --- Güvenlik --------------------------------------------------------------

def _is_private_host(hostname: str) -> bool:
    """Hostname özel/loopback/link-local bir adrese mi çözümleniyor?"""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError):
        return True  # çözümlenemiyorsa güvenli tarafta kal
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


def is_url_allowed(url: str, *, trusted_only: bool = False, allow_private: bool = False) -> tuple[bool, str]:
    """URL'nin çekilmesi güvenli mi? (izin, gerekçe) döndürür.

    ``allow_private`` yalnızca bilinçli yerel servisler için kullanılır
    (ör. Ollama ``localhost:11434``).
    """
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        return False, f"desteklenmeyen şema: {parsed.scheme!r}"
    if not parsed.hostname:
        return False, "host yok"
    if not allow_private:
        try:
            socket.getaddrinfo(parsed.hostname, None)
        except (socket.gaierror, UnicodeError):
            return False, f"host çözümlenemedi: {parsed.hostname}"
        if _is_private_host(parsed.hostname):
            return False, f"özel/loopback adres reddedildi: {parsed.hostname}"
    if trusted_only:
        host = parsed.hostname.lower()
        if not any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS):
            return False, f"beyaz listede değil: {host}"
    return True, "ok"


# --- İstek ----------------------------------------------------------------

def fetch(
    url: str,
    *,
    timeout: float = HTTP_TIMEOUT_MEDIUM,
    max_retries: int = HTTP_MAX_RETRIES,
    trusted_only: bool = False,
    allow_private: bool = False,
    diagnostics: Diagnostics | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> str | None:
    """
    URL'yi çeker ve gövdeyi metin olarak döndürür; başarısızlıkta ``None``.

    Hata asla sessizce yutulmaz — her başarısızlık loglanır ve varsa
    ``diagnostics`` defterine yazılır.
    """
    allowed, reason = is_url_allowed(url, trusted_only=trusted_only, allow_private=allow_private)
    if not allowed:
        logger.warning("URL engellendi (%s): %s", reason, url)
        if diagnostics is not None:
            diagnostics.add(RequestRecord(url=url, status="blocked", duration_ms=0, error=reason))
        return None

    session = get_session()
    started = time.perf_counter()
    last_error: str | None = None
    http_status: int | None = None

    for attempt in range(max_retries + 1):
        try:
            resp = session.get(url, timeout=timeout, headers=headers, params=params)
            http_status = resp.status_code
            if resp.status_code == 200:
                elapsed = int((time.perf_counter() - started) * 1000)
                if diagnostics is not None:
                    diagnostics.add(RequestRecord(url=url, status="ok", duration_ms=elapsed, http_status=200))
                return _decode_body(resp)
            # 429/503 gibi geçici durumlarda tekrar dene, 4xx'te deneme
            last_error = f"HTTP {resp.status_code}"
            if resp.status_code not in (429, 500, 502, 503, 504):
                break
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < max_retries:
            time.sleep(HTTP_BACKOFF_BASE * (2 ** attempt))

    elapsed = int((time.perf_counter() - started) * 1000)
    status = "http_error" if http_status else "network_error"
    logger.warning("İstek başarısız (%s) %s — %s", last_error, url, f"{elapsed}ms")
    if diagnostics is not None:
        diagnostics.add(
            RequestRecord(url=url, status=status, duration_ms=elapsed, http_status=http_status, error=last_error)
        )
    return None


def fetch_json(url: str, **kwargs: Any) -> Any | None:
    """`fetch` ile çeker ve JSON olarak ayrıştırır; başarısızlıkta ``None``."""
    import json

    body = fetch(url, **kwargs)
    if body is None:
        return None
    try:
        return json.loads(body)
    except (ValueError, TypeError) as exc:
        logger.warning("JSON ayrıştırılamadı %s: %s", url, exc)
        return None


# Geriye dönük uyumluluk: eski ad.
fetch_url_safe = fetch


def post_json(
    url: str,
    payload: Any,
    *,
    timeout: float = HTTP_TIMEOUT_MEDIUM,
    allow_private: bool = False,
    diagnostics: Diagnostics | None = None,
) -> Any | None:
    """JSON gövdeli POST atar ve JSON yanıtı döndürür; başarısızlıkta ``None``."""
    allowed, reason = is_url_allowed(url, allow_private=allow_private)
    if not allowed:
        logger.warning("POST URL engellendi (%s): %s", reason, url)
        if diagnostics is not None:
            diagnostics.add(RequestRecord(url=url, status="blocked", duration_ms=0, error=reason))
        return None

    started = time.perf_counter()
    try:
        resp = get_session().post(url, json=payload, timeout=timeout)
        elapsed = int((time.perf_counter() - started) * 1000)
        if resp.status_code == 200:
            if diagnostics is not None:
                diagnostics.add(RequestRecord(url=url, status="ok", duration_ms=elapsed, http_status=200))
            return resp.json()
        logger.warning("POST başarısız HTTP %s: %s", resp.status_code, url)
        if diagnostics is not None:
            diagnostics.add(
                RequestRecord(url=url, status="http_error", duration_ms=elapsed, http_status=resp.status_code)
            )
    except (requests.RequestException, ValueError) as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        logger.warning("POST hatası %s: %s", url, exc)
        if diagnostics is not None:
            diagnostics.add(
                RequestRecord(url=url, status="network_error", duration_ms=elapsed, error=str(exc))
            )
    return None
