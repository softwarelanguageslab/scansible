from collections.abc import Iterable
from collections import defaultdict

from ..models.graph import Graph
from ..models.nodes import Expression, IntermediateValue, Variable
from ..models.edges import Def
from .base import Rule, RuleResult

def is_globally_scoped(scope: int) -> bool:
    return scope in (17, 18)

def partition_local_global(defs: set[tuple[str, int]]) -> tuple[set[str], set[str]]:
    loc, glob = (set(), set())
    for role_name, scope in defs:
        if is_globally_scoped(scope):
            glob.add(role_name)
        else:
            loc.add(role_name)
    return (loc - glob), glob

def getvars(graph: Graph) -> Iterable[tuple[str, int]]:
    for node in graph.nodes():
        if not isinstance(node, Variable):
            continue

        yield (node.name, node.scope_level)

class ConflictingVariables:
    def __init__(self) -> None:
        self.names_to_roles_and_scope: dict[str, set[tuple[str, int]]] = defaultdict(set)
        self.affected_loc: set[str] = set()
        self.causing_glob: set[str] = set()
        self.results: list[str] = []

    def add_all(self, role_name: str, defs: list[tuple[str, int]]) -> None:
        for (name, level) in defs:
            self.names_to_roles_and_scope[name].add((role_name, level))

    def process(self) -> None:
        for name, defs in self.names_to_roles_and_scope.items():
            if len(defs) < 1:
                continue

            loc, glob = partition_local_global(defs)
            if not glob or not loc:
                continue

            self.causing_glob.update(glob)
            self.affected_loc.update(loc)

            self.results.append('\n'.join([
                f'Variable {name} may cause conflicts between roles.',
                f'{len(glob)} role(s) define the variable globally (e.g. {list(glob)[:2]})',
                f'{len(loc)} role(s) define the variable locally (e.g. {list(loc)[:2]})',
                'If any of the latter roles are included after any of the former roles, the latter role will not be able to access the variable'
            ]))


