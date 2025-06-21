from __future__ import annotations

from typing import Any

import sys

import pytest
from loguru import logger

from scansible.representations.pdg import Graph
from test_utils.graph_matchers import create_graph

logger.remove()
logger.add(sys.stderr, format="{level} {message}", level="DEBUG")


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--slow", action="store_true", default=False, help="run slow tests"
    )


def pytest_collection_modifyitems(config: Any, items: Any) -> None:
    if config.getoption("--slow"):
        # --slow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture()
def g() -> Graph:
    g = create_graph({}, [])
    assert g.num_nodes == 0
    return g
