"""
Etimoloji REST API Sunucusu (Local REST API Server)

Web panelinin haberleştiği yerel HTTP sunucusu.

Güvenlik düzeltmeleri
---------------------
* **Bind adresi**: ``('', port)`` tüm ağ arayüzlerine (0.0.0.0) bağlanıyordu;
  aynı ağdaki herkes erişebiliyordu. Varsayılan artık ``127.0.0.1``.
* **CORS**: ``Access-Control-Allow-Origin: *`` idi; herhangi bir web sitesi
  tarayıcı üzerinden bu API'yi sürebiliyordu. Artık yapılandırılmış
  origin listesiyle sınırlı.
* **Hata sızıntısı**: ``str(e)`` ile iç istisna metni (dosya yolları, SQL
  hataları) HTTP 500 gövdesinde istemciye dönüyordu. Artık loglanır,
  istemciye genel mesaj gider (``ETY_API_DEBUG_ERRORS=1`` ile açılabilir).
* **POST**: ``Allow-Methods`` içinde ilan ediliyordu ama ``do_POST`` tanımlı
  değildi. İlandan çıkarıldı.
* **Girdi sınırı**: ``word`` uzunluk denetimi olmadan motora gidiyordu.
* **Eşzamanlılık**: Tek iş parçacıklı ``HTTPServer`` tek yavaş istekte tüm
  sunucuyu blokluyordu. Artık ``ThreadingHTTPServer``.
* **Zorunlu yazma**: Her anonim istek veritabanına yazıyordu (sınırsız disk
  büyümesi). Artık ``save`` parametresiyle denetlenir.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from engine import config
from engine.db.database import DatabaseManager
from engine.logging_setup import configure_logging, get_logger
from engine.search_engine import SearchEngine

logger = get_logger(__name__)

db = DatabaseManager()
engine = SearchEngine(db_manager=db)


class EtymologyAPIHandler(BaseHTTPRequestHandler):
    server_version = "TurkicEtymologyEngine/3.0"

    # --- Yardımcılar -----------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        """Varsayılan stderr çıktısını merkezî logger'a yönlendirir."""
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _allowed_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        if origin and origin in config.CORS_ALLOW_ORIGINS:
            return origin
        if "*" in config.CORS_ALLOW_ORIGINS:
            return "*"
        return None

    def _send_cors_headers(self) -> None:
        origin = self._allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _respond(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str, exc: Exception | None = None) -> None:
        payload: dict[str, Any] = {"error": message}
        if exc is not None:
            logger.error("API hatası (%s): %s", status, message, exc_info=True)
            if config.API_DEBUG_ERRORS:
                payload["detail"] = f"{type(exc).__name__}: {exc}"
        self._respond(status, payload)

    # --- Uç noktalar ------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/search":
            self._handle_search(params)
        elif parsed.path == "/api/list":
            self._handle_list()
        elif parsed.path == "/api/health":
            self._respond(200, {
                "status": "ok",
                "fetcher_count": len(engine.fetchers),
                "live_sources": sum(1 for f in engine.fetchers if not getattr(f, "is_seed_source", False)),
                "seed_sources": sum(1 for f in engine.fetchers if getattr(f, "is_seed_source", False)),
                "cache_enabled": config.CACHE_ENABLED,
            })
        else:
            self._respond(404, {"error": "Bilinmeyen uç nokta."})

    def _handle_search(self, params: dict[str, list[str]]) -> None:
        word_list = params.get("word", [])
        word = (word_list[0] if word_list else "").strip()

        if not word:
            self._error(400, "Kelime parametresi (word) eksik.")
            return
        if len(word) > config.MAX_QUERY_LENGTH:
            self._error(
                400,
                f"Kelime en fazla {config.MAX_QUERY_LENGTH} karakter olabilir.",
            )
            return

        use_ai = params.get("ai", ["false"])[0].lower() == "true"
        save = params.get("save", ["true"])[0].lower() != "false"

        try:
            finding = engine.search(word.lower(), save_to_db=save, use_qwen_agent=use_ai)
        except Exception as exc:
            self._error(500, "Arama sırasında beklenmeyen bir hata oluştu.", exc)
            return
        self._respond(200, finding)

    def _handle_list(self) -> None:
        try:
            findings = db.list_findings()
        except Exception as exc:
            self._error(500, "Kayıtlar listelenemedi.", exc)
            return
        self._respond(200, findings)


def run_server(host: str | None = None, port: int | None = None) -> None:
    configure_logging()
    bind_host = host or config.API_HOST
    bind_port = port or config.API_PORT
    httpd = ThreadingHTTPServer((bind_host, bind_port), EtymologyAPIHandler)
    httpd.daemon_threads = True

    print(f"🚀 Etimoloji REST API: http://{bind_host}:{bind_port}")
    print(f"   CORS izinli origin: {', '.join(config.CORS_ALLOW_ORIGINS) or '(yok)'}")
    print(f"   Önbellek: {'açık' if config.CACHE_ENABLED else 'kapalı'}")
    if bind_host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "Sunucu yerel olmayan bir adrese bağlandı (%s); API kimlik doğrulaması YOKTUR.",
            bind_host,
        )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Sunucu durduruldu.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    cli_port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    run_server(port=cli_port)
