from __future__ import annotations

from typing import Any

from contextlib import contextmanager

import redis


class RedisGraphDatabase:
    def __init__(self, db_host: str) -> None:
        self._redis = redis.Redis(host=db_host)

    @contextmanager
    def temporary_graph(self, name: str, query: str) -> Any:  # type: ignore[misc]
        g: Any = self._redis.graph(name)  # pyright: ignore
        g.query(query)
        try:
            yield g
        finally:
            try:
                g.delete()
            except:
                pass
