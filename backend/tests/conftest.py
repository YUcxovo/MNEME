"""Shared test fixtures, including an in-memory Redis stand-in."""

from collections.abc import AsyncIterator
from fnmatch import fnmatch
from typing import Self

import pytest


class FakePipeline:
    """Queue-and-execute pipeline matching the redis-py asyncio surface."""

    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def incrbyfloat(self, key: str, amount: float) -> Self:
        self._commands.append(("incrbyfloat", (key, amount), {}))
        return self

    def expire(self, key: str, seconds: int, nx: bool = False) -> Self:
        self._commands.append(("expire", (key, seconds), {"nx": nx}))
        return self

    async def execute(self) -> list[object]:
        results: list[object] = []
        for name, args, kwargs in self._commands:
            results.append(await getattr(self._redis, name)(*args, **kwargs))
        self._commands.clear()
        return results

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeRedis:
    """Minimal in-memory Redis with decode_responses=True semantics."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                self.ttls.pop(key, None)
                deleted += 1
        return deleted

    async def incrbyfloat(self, key: str, amount: float) -> float:
        value = float(self.store.get(key, "0")) + amount
        self.store[key] = repr(value)
        return value

    async def expire(self, key: str, seconds: int, nx: bool = False) -> bool:
        if key not in self.store or (nx and key in self.ttls):
            return False
        self.ttls[key] = seconds
        return True

    async def scan_iter(self, match: str | None = None) -> AsyncIterator[str]:
        for key in list(self.store):
            if match is None or fnmatch(key, match):
                yield key

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)


@pytest.fixture
def fake_redis() -> FakeRedis:
    """Fresh in-memory Redis per test."""
    return FakeRedis()
