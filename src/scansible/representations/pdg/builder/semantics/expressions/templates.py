"""Extract information from template expressions."""

from __future__ import annotations

from typing import final

from collections.abc import Container, Iterable, Sequence
from functools import cached_property

from jinja2 import nodes
from jinja2.compiler import DependencyFinderVisitor
from jinja2.visitor import NodeVisitor

from scansible.representations import ast

from .constants import ANSIBLE_GLOBALS, PURE_FILTERS, PURE_LOOKUP_PLUGINS, PURE_TESTS


class FindUndeclaredVariablesVisitor(NodeVisitor):
    def __init__(self, declared: frozenset[str]) -> None:
        self.declared: set[str] = set(declared)
        self.undeclared: set[str] = set()

    def visit_Name(self, name_node: nodes.Name) -> None:  # noqa: N802
        if name_node.ctx == "load" and name_node.name not in self.declared:
            self.undeclared.add(name_node.name)
        else:
            self.declared.add(name_node.name)

    def visit_Block(self, _block_node: nodes.Block) -> None:  # noqa: N802
        # Don't visit blocks, they may have local declarations.
        # Not sure if we'd ever need to visit blocks.
        pass


@final
class TemplateExpressionAST:
    def __init__(self, expression: ast.Expression) -> None:
        self.ast_root = expression.template
        self.raw = expression.raw

    @cached_property
    def referenced_variables(self) -> set[str]:
        var_visitor = FindUndeclaredVariablesVisitor(ANSIBLE_GLOBALS)
        var_visitor.visit(self.ast_root)
        return var_visitor.undeclared

    @cached_property
    def impure_components(self) -> Sequence[str]:
        """The components that make this expression impure."""
        return tuple(self._get_impure_components())

    @cached_property
    def is_pure(self) -> bool:
        """Whether this expression is pure, i.e., returns the same value if the input values remain the same."""
        return not self.impure_components

    def _get_calls_to(self, names: Container[str]) -> Sequence[nodes.Call]:
        """Return all call nodes to certain functions."""
        return [
            call_node
            for call_node in self.ast_root.find_all(nodes.Call)
            if isinstance(call_node.node, nodes.Name) and call_node.node.name in names
        ]

    def _get_impure_components(self) -> Iterable[str]:
        dep_visitor = DependencyFinderVisitor()
        dep_visitor.visit(self.ast_root)

        if self._get_calls_to(("now",)):
            yield "function 'now'"

        yield from (f"filter '{op}'" for op in (dep_visitor.filters - PURE_FILTERS))
        yield from (f"test '{op}'" for op in (dep_visitor.tests - PURE_TESTS))

        for call in self._get_calls_to(("lookup", "query", "q")):
            target = call.args[0]
            if not isinstance(target, nodes.Const):
                yield f"lookup of non-constant ({target.__class__.__name__})"
            elif target.value not in PURE_LOOKUP_PLUGINS:  # pyright: ignore[reportAny]
                yield f"lookup {target.value!r}"  # pyright: ignore[reportAny]
