import sys
import os

import pytest
from loguru import logger

from scansible.representations.pdg import Graph

sys.path.append(os.path.join(os.path.dirname(__file__), 'helpers'))

logger.remove()
logger.add(sys.stderr, format='{level} {message}', level='DEBUG')

from graph_matchers import create_graph  # type: ignore[import]


@pytest.fixture()
def g() -> Graph:
    g = create_graph({}, [])
    assert len(g) == 0
    return g  # type: ignore[no-any-return]
