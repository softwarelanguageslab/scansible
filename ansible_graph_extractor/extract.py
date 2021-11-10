from __future__ import annotations

import sys
from pathlib import Path
from io import StringIO

from loguru import logger

from .io.structural_models import parse_role
from .extractor.main import extract_structural_graph
from .io import neo4j, graphml, graphviz

def extract_one(args: tuple[str, Path], log_reset: bool = True) -> tuple[str, str, str, str, str] | tuple[str, Exception]:
    log_stream = StringIO()
    if log_reset:
        logger.remove()
        logger.add(log_stream, level='DEBUG')
    role_id, role_path = args
    try:
        srm = parse_role(role_path, role_id)
        sg = extract_structural_graph(srm)
        neo4j_str = neo4j.dump_graph(sg)
        graphml_str = graphml.dump_graph(sg)
        dot_str = graphviz.dump_graph(sg)
        error_str = '\n'.join(sg.errors)
        log_stream.seek(0)
        log_str = log_stream.read()
        return role_id, neo4j_str, graphml_str, dot_str, error_str, log_str
    except Exception as e:
        return role_id, e
    finally:
        if log_reset:
            logger.remove()
