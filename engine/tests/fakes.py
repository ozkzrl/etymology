"""
Test İkizleri (Test Doubles)

``BaseFetcher`` sözleşmesine uyan sahte toplayıcılar. ``SearchEngine`` artık
fetcher listesini enjekte etmeye izin verdiği için (``fetchers=...``) tüm
entegrasyon testleri ağsız çalışabilir.
"""
from __future__ import annotations

from typing import Any

from engine.fetchers.base import BaseFetcher


class FakeFetcher(BaseFetcher):
    """Verilen kayıtları döndüren sahte toplayıcı."""

    def __init__(
        self,
        name: str = "Sahte Kaynak",
        entries: list[tuple[str, str]] | None = None,
        meaning: str = "test anlamı",
        proto: str = "",
        seed: bool = False,
        first_attestation: dict[str, Any] | None = None,
        only_for: str | None = None,
    ):
        self._name = name
        self._entries = entries or []
        self._meaning = meaning
        self._proto = proto
        self.is_seed_source = seed
        self._attestation = first_attestation
        self._only_for = only_for
        self.calls: list[str] = []

    @property
    def source_name(self) -> str:
        return self._name

    def fetch(self, word: str) -> dict[str, Any]:
        self.calls.append(word)
        result = self.empty_result()
        if self._only_for is not None and word != self._only_for:
            return result
        result["root"] = {
            "proto_turkic": self._proto,
            "meaning": self._meaning,
            "reconstruction_notes": "",
        }
        for code, form in self._entries:
            result["turkic_languages"].append(self.make_entry(code, form, self._meaning))
        if self._attestation:
            result["first_attestation"] = self._attestation
        return result


class FailingFetcher(BaseFetcher):
    """Her çağrıda istisna fırlatan toplayıcı — hata izolasyonu testi için."""

    def __init__(self, name: str = "Patlayan Kaynak", exc: type[Exception] = RuntimeError):
        self._name = name
        self._exc = exc

    @property
    def source_name(self) -> str:
        return self._name

    def fetch(self, word: str) -> dict[str, Any]:
        raise self._exc(f"kaynak çöktü: {word}")


class EmptyFetcher(BaseFetcher):
    """Hiç veri döndürmeyen toplayıcı."""

    def __init__(self, name: str = "Boş Kaynak"):
        self._name = name

    @property
    def source_name(self) -> str:
        return self._name

    def fetch(self, word: str) -> dict[str, Any]:
        return self.empty_result()


class SlowFetcher(BaseFetcher):
    """Belirli süre bekleyen toplayıcı — paralellik testi için."""

    def __init__(self, name: str = "Yavaş Kaynak", delay: float = 0.05):
        self._name = name
        self._delay = delay

    @property
    def source_name(self) -> str:
        return self._name

    def fetch(self, word: str) -> dict[str, Any]:
        import time

        time.sleep(self._delay)
        return self.empty_result()
