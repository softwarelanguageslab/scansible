from __future__ import annotations

import sys
from collections.abc import Sequence

import pytest
from graph_matchers import create_graph  # pyright: ignore[reportImplicitRelativeImport]
from loguru import logger

from scansible.representations.pdg import Graph

logger.remove()
_ = logger.add(sys.stderr, format="{level} {message}", level="DEBUG")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--slow", action="store_true", default=False, help="run slow tests"
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: Sequence[pytest.Item]
) -> None:
    if config.getoption("--slow"):
        # --slow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture
def g() -> Graph:
    g = create_graph({}, [])
    assert g.num_nodes == 0
    return g
