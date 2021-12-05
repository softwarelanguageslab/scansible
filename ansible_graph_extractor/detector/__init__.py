from pathlib import Path

from ..io import graphml
from ..models.graph import Graph
from .base import RuleResult
from .reuse_dynamic_rule import ReuseDynamicExpressionRule
from .reuse_changed_rule import ReuseChangedVariableRule
from .unnecessary_set_fact import UnnecessarySetFactRule
from .conflicting_variables import getvars

ALL_RULES = [ReuseDynamicExpressionRule(), ReuseChangedVariableRule(), UnnecessarySetFactRule()]

def detect_all(graph: Graph) -> list[RuleResult]:
    return [res for rule in ALL_RULES for res in rule.scan(graph)]

def detect_one_graph(graphml_path: Path) -> tuple[str, list[RuleResult], list[tuple[str, int]]] | tuple[Path, Exception]:
    try:
        graph = graphml.import_graph(graphml_path.read_text())
        results = detect_all(graph)

        return graph.role_name, results, list(getvars(graph))
    except Exception as err:
        return graphml_path, err
