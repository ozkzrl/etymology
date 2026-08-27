"""
REST API Sunucusu ve CLI Testleri

Her iki modül de daha önce **hiç test edilmemişti** (%0 kapsam).
Güvenlik regresyonları burada kilitlenir.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer

from engine import config, server
from engine.db.database import DatabaseManager
from engine.search_engine import SearchEngine
from engine.tests.fakes import FakeFetcher

GOZ_FORMS = [("tr", "göz"), ("kk", "көз"), ("cv", "куҫ"), ("tt", "күз")]


class ServerHarness:
    """Gerçek bir HTTP sunucusunu yerel portta ayağa kaldırır."""

    def __init__(self, fetchers=None):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = DatabaseManager(self.db_path)
        server.db = self.db
        server.engine = SearchEngine(
            db_manager=self.db,
            fetchers=fetchers or [FakeFetcher(entries=GOZ_FORMS, meaning="göz", only_for="göz")],
        )
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.EtymologyAPIHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def url(self, path: str) -> str:
        # ASCII dışı karakterler URL'de kodlanmalıdır (http.client ascii bekler)
        safe = urllib.parse.quote(path, safe="/?&=")
        return f"http://127.0.0.1:{self.port}{safe}"

    def get(self, path: str, headers: dict | None = None):
        req = urllib.request.Request(self.url(path), headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, dict(resp.headers), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode("utf-8")


class TestServerEndpoints(unittest.TestCase):
    def test_health(self):
        with ServerHarness() as h:
            status, _, body = h.get("/api/health")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["status"], "ok")
            self.assertIn("live_sources", data)
            self.assertIn("seed_sources", data)

    def test_search_returns_finding(self):
        with ServerHarness() as h:
            status, _, body = h.get("/api/search?word=göz&save=false")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["query_word"], "göz")
            self.assertEqual(data["root"]["proto_turkic"], "*köŕ")
            self.assertIn("diagnostics", data)

    def test_missing_word_is_400(self):
        with ServerHarness() as h:
            status, _, body = h.get("/api/search")
            self.assertEqual(status, 400)
            self.assertIn("error", json.loads(body))

    def test_overlong_word_is_rejected(self):
        """Girdi uzunluğu sınırlanmalıdır (amplifikasyon koruması)."""
        with ServerHarness() as h:
            status, _, body = h.get("/api/search?word=" + "a" * 300)
            self.assertEqual(status, 400)
            self.assertIn("karakter", json.loads(body)["error"])

    def test_list_endpoint(self):
        with ServerHarness() as h:
            h.get("/api/search?word=göz&save=true")
            status, _, body = h.get("/api/list")
            self.assertEqual(status, 200)
            self.assertTrue(any(f["query_word"] == "göz" for f in json.loads(body)))

    def test_unknown_endpoint_is_404(self):
        with ServerHarness() as h:
            status, _, _ = h.get("/api/does-not-exist")
            self.assertEqual(status, 404)

    def test_save_false_does_not_persist(self):
        with ServerHarness() as h:
            h.get("/api/search?word=göz&save=false")
            self.assertIsNone(h.db.get_finding("göz"))


class TestServerSecurity(unittest.TestCase):
    """Güvenlik regresyonları."""

    def test_default_bind_is_loopback(self):
        """Sunucu varsayılan olarak 0.0.0.0'a bağlanmamalıdır."""
        self.assertEqual(config.API_HOST, "127.0.0.1")

    def test_cors_rejects_unknown_origin(self):
        """CORS `*` OLMAMALIDIR."""
        with ServerHarness() as h:
            _, headers, _ = h.get("/api/health", {"Origin": "https://evil.example.com"})
            self.assertIsNone(headers.get("Access-Control-Allow-Origin"))

    def test_cors_allows_configured_origin(self):
        with ServerHarness() as h:
            _, headers, _ = h.get("/api/health", {"Origin": "http://localhost:3000"})
            self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://localhost:3000")

    def test_errors_do_not_leak_internals(self):
        """HTTP 500 gövdesi iç istisna metni İÇERMEMELİDİR."""

        class Boom(FakeFetcher):
            pass

        with ServerHarness() as h:
            def explode(*a, **k):
                raise RuntimeError("/gizli/dosya/yolu.db kilitli")

            server.engine.search = explode
            status, _, body = h.get("/api/search?word=test")
            self.assertEqual(status, 500)
            self.assertNotIn("gizli", body)
            self.assertNotIn("RuntimeError", body)

    def test_post_is_not_advertised(self):
        """Tanımsız POST metodu CORS başlığında İLAN EDİLMEMELİDİR."""
        with ServerHarness() as h:
            _, headers, _ = h.get("/api/health", {"Origin": "http://localhost:3000"})
            self.assertNotIn("POST", headers.get("Access-Control-Allow-Methods", ""))

    def test_nosniff_header(self):
        with ServerHarness() as h:
            _, headers, _ = h.get("/api/health")
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")


class TestCli(unittest.TestCase):
    """CLI komutları — daha önce %0 kapsam."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = DatabaseManager(self.db_path)
        self.db.save_finding({
            "query_word": "göz",
            "morphology": "Yalın Kök",
            "root": {"proto_turkic": "*köŕ", "meaning": "göz", "reconstruction_notes": ""},
            "turkic_languages": [
                {"lang_code": "kk", "lang_name": "Kazakça", "word": "көз",
                 "meaning": "göz", "script": "Cyrillic"}
            ],
            "sources": ["Test"],
        })

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _run(self, argv, engine_fetchers=None):
        """CLI'yi verilen argümanlarla çalıştırır ve stdout'u döndürür."""
        import sys

        from engine import cli

        buf = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["etimoloji", *argv]
        orig_db, orig_engine = cli.DatabaseManager, cli.SearchEngine
        cli.DatabaseManager = lambda *a, **k: self.db
        cli.SearchEngine = lambda *a, **k: SearchEngine(
            db_manager=self.db,
            fetchers=engine_fetchers or [FakeFetcher(entries=GOZ_FORMS, meaning="göz", only_for="göz")],
        )
        try:
            with redirect_stdout(buf):
                try:
                    cli.main()
                except SystemExit as e:
                    return buf.getvalue(), (e.code or 0)
            return buf.getvalue(), 0
        finally:
            sys.argv = old_argv
            cli.DatabaseManager, cli.SearchEngine = orig_db, orig_engine

    def test_list_command(self):
        out, code = self._run(["list"])
        self.assertEqual(code, 0)
        self.assertIn("göz", out)

    def test_show_command(self):
        out, code = self._run(["show", "göz"])
        self.assertEqual(code, 0)
        self.assertIn("köŕ", out)

    def test_show_missing_word_exits_nonzero(self):
        _, code = self._run(["show", "yokboylekelime"])
        self.assertNotEqual(code, 0)

    def test_show_json(self):
        out, code = self._run(["show", "göz", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["query_word"], "göz")

    def test_search_command(self):
        out, code = self._run(["search", "göz", "--no-save"])
        self.assertEqual(code, 0)
        self.assertIn("göz", out)

    def test_search_json(self):
        out, code = self._run(["search", "göz", "--json", "--no-save"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["root"]["proto_turkic"], "*köŕ")

    def test_export_command_writes_cldf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, code = self._run(["export", "göz", "--out", tmp])
            self.assertEqual(code, 0)
            for name in ("forms.csv", "cognates.csv", "cldf-metadata.json"):
                self.assertTrue(os.path.exists(os.path.join(tmp, name)), name)

    def test_export_missing_word_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, code = self._run(["export", "yokboyle", "--out", tmp])
            self.assertNotEqual(code, 0)

    def test_no_command_shows_help(self):
        _, code = self._run([])
        self.assertNotEqual(code, 0)

    def test_validate_command(self):
        out, code = self._run(["validate", "göz", "--origin", "*köŕ"])
        self.assertEqual(code, 0)
        self.assertTrue(out.strip())


if __name__ == "__main__":
    unittest.main()
