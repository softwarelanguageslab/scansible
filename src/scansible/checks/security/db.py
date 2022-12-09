from __future__ import annotations

from contextlib import AbstractContextManager

from neo4j import GraphDatabase, Driver, Record


class Neo4jDatabase(AbstractContextManager['Neo4jDatabase']):
    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._auth = (user, password)
        self._driver: Driver | None = None


    def __enter__(self) -> Neo4jDatabase:
        assert self._driver is None, f'{self.__class__.__name__} is not re-entrant as a context manager'
        self._driver = GraphDatabase.driver(self._uri, auth=self._auth)
        return self

    def __exit__(self, *_: object) -> None:
        assert self._driver is not None, 'Context manager not entered'
        self._driver.close()
        self._driver = None

    def run(self, query: str) -> list[Record]:
        assert self._driver is not None, 'Driver not initialised'

        with self._driver.session() as session:
            return list(session.run(query))

