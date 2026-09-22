from __future__ import annotations

import textwrap
from collections import defaultdict
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path

from scansible import ast
from scansible.utils import HasLocation, Location, join_sequences

from .. import representation as rep
from .semantics import ExpressionManager, InclusionManager, VariableManager


class BuildContext:
    vars: VariableManager
    expr: ExpressionManager
    graph: rep.Graph
    include_ctx: InclusionManager
    model_root: ast.Role | ast.Playbook
    errors: list[tuple[str, Location]]
    _next_iv_id: int

    handler_notifications: dict[str, set[rep.Task]]
    active_conditions: Sequence[rep.DataNode]
    active_loops: Sequence[rep.DataNode]

    def __init__(
        self,
        graph: rep.Graph,
        model: ast.AST,
        role_search_paths: Sequence[Path],
        *,
        lenient: bool,
    ) -> None:
        self.vars = VariableManager(self)
        self.expr = ExpressionManager(self)
        self.graph = graph
        self.model_root = model.root
        self.include_ctx = InclusionManager(model, role_search_paths, lenient=lenient)
        self._next_iv_id = 0
        self.errors = []
        self.handler_notifications = defaultdict(set)
        self.active_conditions = []
        self.active_loops = []

    @contextmanager
    def activate_conditions(self, conditions: list[rep.DataNode]) -> Generator[None]:
        old_conditions = self.active_conditions
        self.active_conditions = join_sequences(old_conditions, conditions)
        try:
            yield
        finally:
            self.active_conditions = old_conditions

    @contextmanager
    def activate_loop(self, loop_data_node: rep.DataNode) -> Generator[None]:
        old_loops = self.active_loops
        self.active_loops = join_sequences(old_loops, [loop_data_node])
        try:
            yield
        finally:
            self.active_loops = old_loops

    def next_iv_id(self) -> int:
        self._next_iv_id += 1
        return self._next_iv_id - 1

    def get_location(self, ds: object) -> rep.NodeLocation:
        loc = ds.__location__ if isinstance(ds, HasLocation) else Location.synthetic()

        return rep.NodeLocation(
            path=loc.path,
            start=loc.start,
            end=loc.end,
            includer_location=self.include_ctx.last_include_location,
        )

    def record_build_error(self, reason: str, location: Location) -> None:
        self.errors.append((reason, location))

    def summarise_build_errors(self) -> str:
        reason_to_location: dict[str, list[Location]] = defaultdict(list)
        for reason, location in self.errors:
            reason_to_location[reason.strip()].append(location)

        parts: list[str] = []
        for reason, locations in sorted(reason_to_location.items()):
            num_unknown = len([loc for loc in locations if loc.is_synthetic])
            loc_strs = sorted({str(loc) for loc in locations if not loc.is_synthetic})
            if num_unknown:
                prefix = "and " if loc_strs else ""
                loc_strs.append(f"{prefix}{num_unknown} unknown location(s)")
            locs = textwrap.indent("\n".join(loc_strs), " " * 4)
            parts.append(f"{reason}\n{locs}")

        return "\n\n".join(parts)

    @property
    def file_set(self) -> frozenset[Path]:
        return frozenset(self.include_ctx.all_included_files)
