import sys
import os

import pytest
from loguru import logger

from scansible.representations.pdg import Graph
from test_utils.graph_matchers import create_graph

logger.remove()
logger.add(sys.stderr, format='{level} {message}', level='DEBUG')


@pytest.fixture()
def g() -> Graph:
    g = create_graph({}, [])
    assert len(g) == 0
    return g
