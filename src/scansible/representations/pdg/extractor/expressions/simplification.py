from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from jinja2 import nodes
from loguru import logger

from scansible.utils import FrozenDict, first

from .templates import TemplateExpressionAST
from .var_context import VarContext


@dataclass(frozen=True)
class SimplifiedExpression:
    ast: nodes.Output
    var_mappings: Mapping[str, str]
    conditions: Sequence[object]  # TODO!
    skip_nodes: int = 0  # Used to prevent infinitely retrying non-inlinable nodes.

    @classmethod
    def empty(cls, ast: nodes.Template) -> SimplifiedExpression:
        assert len(ast.body) == 1 and isinstance(ast.body[0], nodes.Output)
        return cls(ast.body[0], FrozenDict({}), tuple())

    def to_regex(self) -> str:
        re_str = ""
        prev_is_wildcard = False
        for node in self.ast.nodes:
            if isinstance(node, nodes.TemplateData):
                prev_is_wildcard = False
                re_str += re.escape(node.data)
            elif not prev_is_wildcard:
                # Prevent immediately-adjacent wildcards
                prev_is_wildcard = True
                re_str += "(.+)"

        return re_str


def simplify_expression(
    ast: nodes.Template, var_ctx: VarContext
) -> set[SimplifiedExpression]:
    """Simplify an expression by performing constant propagation.

    Returns a list of possible expressions. Multiple results are possible
    because used variables may have multiple possible values.
    """
    if len(ast.body) != 1 or not isinstance(ast.body[0], nodes.Output):
        return {SimplifiedExpression.empty(ast)}

    changed = True
    finalized: set[SimplifiedExpression] = {SimplifiedExpression.empty(ast)}
    while changed:
        worklist = finalized
        finalized = set()
        changed = False

        for to_simplify in worklist:
            result = list(_simplify(to_simplify, var_ctx))
            changed = changed or len(result) > 1 or result[0] != to_simplify
            finalized |= set(result)

    return finalized


def _simplify(
    expr: SimplifiedExpression, var_ctx: VarContext
) -> Iterable[SimplifiedExpression]:
    """Replace top-level variable references with their initialisers.

    Can return multiple results if there are multiple possible initialisers.
    Returns input if no more simplification can take place.
    """
    first_inlinable_node_idx = first(
        idx
        for idx, node in enumerate(expr.ast.nodes)
        if isinstance(node, nodes.Name)
        and node.ctx == "load"
        and idx >= expr.skip_nodes
    )
    if first_inlinable_node_idx is None:
        yield expr
        return

    pre_nodes = expr.ast.nodes[:first_inlinable_node_idx]
    inline_node = expr.ast.nodes[first_inlinable_node_idx]
    post_nodes = expr.ast.nodes[first_inlinable_node_idx + 1 :]
    assert isinstance(inline_node, nodes.Name)

    inlined_candidates = _get_inlined_candidates(inline_node, var_ctx, expr)
    for cand in inlined_candidates:
        if cand is None:
            yield SimplifiedExpression(
                expr.ast,
                expr.var_mappings,
                expr.conditions,
                skip_nodes=first_inlinable_node_idx + 1,
            )
        else:
            yield SimplifiedExpression(
                nodes.Output(pre_nodes + cand.ast.nodes + post_nodes),
                cand.var_mappings,
                cand.conditions,
            )


def _get_inlined_candidates(
    var_ref: nodes.Name, var_ctx: VarContext, expr: SimplifiedExpression
) -> Iterable[SimplifiedExpression | None]:
    """Inline a variable reference node, return a simplified expression of the
    inlined reference. Expands the input expression's var mappings and conditions
    if necessary.
    """
    var_inits = var_ctx.get_initialisers(var_ref.name, expr.var_mappings)
    if not var_inits:
        logger.debug(f"Cannot simplify reference {var_ref!r}, no initialisers found")
        yield None
        return

    for var_init, new_var_mappings in var_inits:
        if not var_ctx.is_template(var_init) or not isinstance(var_init, str):
            if isinstance(var_init, (list, tuple, Mapping)):
                logger.debug(
                    f"Cannot simplify reference {var_ref!r}, initialiser is composite"
                )
                yield None
            else:
                logger.debug(f"Simplified reference {var_ref!r} to {var_init!r}")
                yield SimplifiedExpression(
                    nodes.Output([nodes.TemplateData(str(var_init))]),
                    FrozenDict(expr.var_mappings | new_var_mappings),
                    expr.conditions,
                )
            continue

        logger.debug(
            f"Performing nested simplification of reference {var_ref!r}'s initialiser {var_init!r}"
        )
        ref_ast = TemplateExpressionAST.parse(var_init)
        if ref_ast is None:
            yield None
            continue

        assert isinstance(ref_ast.ast_root, nodes.Template)
        assert isinstance(ref_ast.ast_root.body[0], nodes.Output)
        yield SimplifiedExpression(
            ref_ast.ast_root.body[0],
            FrozenDict(expr.var_mappings | new_var_mappings),
            expr.conditions,
        )
