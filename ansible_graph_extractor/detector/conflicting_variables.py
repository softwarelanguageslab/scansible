from collections.abc import Callable, Iterable
from collections import defaultdict
from pathlib import Path
import csv

from ..models.graph import Graph
from ..models.nodes import Expression, IntermediateValue, Variable
from ..models.edges import Def
from ..extractor.var_context import ScopeLevel
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


def retain_only_highest(var_defs: list[tuple[str, int]]) -> list[tuple[str, int]]:
    seen: set[str] = set()
    newlist: list[tuple[str, int]] = []
    for role_name, scope in var_defs:
        if role_name not in seen:
            newlist.append((role_name, scope))
            seen.add(role_name)
    return newlist


def find_index(lst: list[tuple[str, int]], pred: Callable[[tuple[str, int]], bool], start_idx: int = 0) -> int | None:
    search_lst = lst[start_idx:]
    for idx, item in enumerate(search_lst):
        if pred(item):
            return idx + start_idx

    return None


class ConflictingVariables:
    def __init__(self, out_path: Path) -> None:
        self.roles: set[str] = set()
        self.out_path = out_path
        self.roles_to_variables_and_scope: dict[str, set[tuple[str, int]]] = defaultdict(set)
        self.names_to_roles_and_scope: dict[str, set[tuple[str, int]]] = defaultdict(set)
        # var_name, hi_role, hi_prec, lo_role, lo_prec
        self.results: list[tuple[str, str, int, str, int]] = []

    def add_all(self, role_name: str, defs: list[tuple[str, int]]) -> None:
        self.roles.add(role_name)
        for (name, level) in defs:
            self.names_to_roles_and_scope[name].add((role_name, level))
            self.roles_to_variables_and_scope[role_name].add((name, level))

    def compute_and_write_stats(self) -> None:
        max_var_defs: dict[tuple[str, str], int] = defaultdict(lambda: 0)
        for role_name, role_defs in self.roles_to_variables_and_scope.items():
            for (var_name, scope) in role_defs:
                idx = (role_name, var_name)
                max_var_defs[idx] = max(max_var_defs[idx], scope)

        with (self.out_path / 'roles.csv').open('w') as f:
            csv_out = csv.writer(f)
            csv_out.writerow(['role_name'])
            for role_name in self.roles:
                csv_out.writerow([role_name])

        with (self.out_path / 'defined_variables.csv').open('w') as f:
            csv_out = csv.writer(f)
            csv_out.writerow(['role_name', 'var_name', 'precedence_level'])
            for (role_name, var_name), var_scope in max_var_defs.items():
                scope_str = ScopeLevel(var_scope).name
                csv_out.writerow([role_name, var_name, scope_str])

    def process(self) -> None:
        self.compute_and_write_stats()
        self.find_conflicts_and_write()

    def find_conflicts_and_write(self) -> None:
        for var_name, var_def_set in self.names_to_roles_and_scope.items():
            # Sort the definitions in precedence order (highest first)
            var_defs = sorted(var_def_set, key=lambda var_def: var_def[1], reverse=True)
            # Retain only the highest precedence definition per role
            var_defs = retain_only_highest(var_defs)
            # Throw out anything with precedence higher than set_fact/register
            # They are locally scoped, so they cannot cause conflicts
            var_defs = [vd for vd in var_defs if vd[1] <= ScopeLevel.SET_FACTS_REGISTERED.value]

            for idx, (role_name, scope) in enumerate(var_defs):
                if scope < ScopeLevel.INCLUDE_VARS.value:
                    # These cannot cause conflicts anymore
                    break

                # The current variable definition in this role may conflict
                # with any variable whose variable with the same name has lower
                # precedence
                # Find first index of a variable with lower precedence
                lower_idx = find_index(var_defs, lambda var_def: var_def[1] < scope, idx + 1)
                if lower_idx is None:
                    # There are no variables with a lower precedence any more,
                    # so we don't need to check anything else for this variable
                    # name
                    break
                self.results.extend((var_name, role_name, scope, *lo) for lo in var_defs[lower_idx:])

        # results now contains ALL possible conflicts. Write them out.
        with (self.out_path / 'conflicts.csv').open('w') as f:
            writer = csv.writer(f)
            writer.writerow(['var_name', 'high_role', 'high_precedence_level', 'low_role', 'low_precedence_level'])
            for var_name, hi_role, hi_level, lo_role, lo_level in self.results:
                hi_level_name = ScopeLevel(hi_level).name
                lo_level_name = ScopeLevel(lo_level).name
                writer.writerow([var_name, hi_role, hi_level_name, lo_role, lo_level_name])
