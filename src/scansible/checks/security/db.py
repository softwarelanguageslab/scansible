from __future__ import annotations

from typing import Any

from contextlib import contextmanager

import redis


class RedisGraphDatabase:
    def __init__(self) -> None:
        self._redis = redis.Redis()

    @contextmanager
    def temporary_graph(self, name: str, query: str) -> Any:  # type: ignore[misc]
        g = self._redis.graph(name)
        g.query(query)
        try:
            yield g
        finally:
            g.delete()
