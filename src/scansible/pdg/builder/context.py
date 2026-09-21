from __future__ import annotations

from typing import cast

import json
import textwrap
from collections import defaultdict
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path

from scansible import ast
from scansible.utils import Position, Positioned, join_sequences

from .. import representation as rep
from .semantics import ExpressionManager, InclusionManager, VariableManager


class VisibilityInformation:
    def __init__(self) -> None:
        self._store: dict[tuple[str, int], set[tuple[str, int]]] = {}

    def set_info(
        self, var_name: str, def_version: int, visible_definitions: set[tuple[str, int]]
    ) -> None:
        assert (var_name, def_version) not in self._store, (
            f"Internal Error: Visibility information already set for {var_name}@{def_version}"
        )
        self._store[(var_name, def_version)] = visible_definitions

    def get_info(self, var_name: str, def_version: int) -> set[tuple[str, int]]:
        assert (var_name, def_version) in self._store, (
            f"Internal Error: Visibility information not stored for {var_name}@{def_version}"
        )
        return self._store[(var_name, def_version)]

    def dump(self) -> str:
        """Dump to JSON."""
        as_lists = [
            [list(k), [list(v) for v in vals]] for k, vals in self._store.items()
        ]
        return json.dumps(as_lists)


class BuildContext:
    vars: VariableManager
    expr: ExpressionManager
    graph: rep.Graph
    include_ctx: InclusionManager
    model_root: ast.Role | ast.Playbook
    # Auxiliary information about variable visibility. We don't store this in
    # the graph itself but in a companion file.
    visibility_information: VisibilityInformation
    errors: list[tuple[str, Position | None]]
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
        self.visibility_information = VisibilityInformation()
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
        if isinstance(ds, Positioned) and not ds.__position__.is_synthetic:
            file = str(ds.__position__.path)
            line, column = ds.__position__.start.line, ds.__position__.start.column
        elif hasattr(ds, "location"):
            file, line, column = cast(tuple[str, int, int], ds.location)  # pyright: ignore[reportAttributeAccessIssue]
        else:
            return rep.NodeLocation.synthetic()

        return rep.NodeLocation(
            file=file,
            line=line,
            column=column,
            includer_location=self.include_ctx.last_include_location,
        )

    def record_build_error(self, reason: str, position: Position | None) -> None:
        self.errors.append((reason, position))

    def summarise_build_errors(self) -> str:
        reason_to_location: dict[str, list[Position | None]] = defaultdict(list)
        for reason, location in self.errors:
            reason_to_location[reason.strip()].append(location)

        parts: list[str] = []
        for reason, locations in sorted(reason_to_location.items()):
            num_unknown = len([loc for loc in locations if loc is None])
            loc_strs = sorted(
                {":".join(map(str, loc)) for loc in locations if loc is not None}
            )
            if num_unknown:
                prefix = "and " if loc_strs else ""
                loc_strs.append(f"{prefix}{num_unknown} unknown location(s)")
            locs = textwrap.indent("\n".join(loc_strs), " " * 4)
            parts.append(f"{reason}\n{locs}")

        return "\n\n".join(parts)

    @property
    def file_set(self) -> frozenset[Path]:
        return frozenset(self.include_ctx.all_included_files)
