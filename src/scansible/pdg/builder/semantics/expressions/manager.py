"""Logic related to variables and expression evaluation during PDG construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, final

from collections import defaultdict

from loguru import logger

from scansible import ast
from scansible.pdg import representation as rep

from ..variables import EnvironmentType, VariableDefinitionRecord
from .templates import TemplateExpressionAST

if TYPE_CHECKING:
    from ...context import BuildContext


class RecursiveDefinitionError(Exception):
    pass


_ValRevisionMap = dict[VariableDefinitionRecord, int]


def extract_type_name(value: ast.AnyExpression) -> rep.ValidTypeStr:
    if value is None:
        return "NoneType"
    if isinstance(value, ast.StrLiteral) and value.is_vaulted:
        return "VaultValue"

    type_name = type(value).__name__.removesuffix("Literal").lower()
    return cast(rep.ValidTypeStr, type_name)


# TODO: Maybe simplify single-variable templates ("{{ var }}") to bypass
# intermediate values?
@final
class ExpressionManager:
    """Manages expression evaluation."""

    def __init__(self, context: BuildContext) -> None:
        self.build_ctx = context
        self._next_val_revisions: _ValRevisionMap = defaultdict(lambda: 0)

    def _get_next_val_revision(self, var_def: VariableDefinitionRecord) -> int:
        self._next_val_revisions[var_def] += 1
        return self._next_val_revisions[var_def] - 1

    def build_expression(self, expr: ast.AnyExpression) -> rep.DataNode:
        if isinstance(expr, ast.Expression):
            return self._build_expression(TemplateExpressionAST(expr))
        if isinstance(expr, ast.SeqLiteral):
            return self._build_sequence_expression(expr)
        if isinstance(expr, ast.MapLiteral):
            return self._build_mapping_expression(expr)
        return self._build_scalar_literal(expr)

    def _build_mapping_expression(
        self, expr: ast.MapLiteral[ast.ScalarLiteral, ast.AnyExpression]
    ) -> rep.DataNode:
        parent_node = rep.CompositeLiteral(type=extract_type_name(expr))
        self.build_ctx.graph.add_node(parent_node)

        for k, v in expr.items():
            child_node = self.build_expression(v)
            key_str = str(k)
            self.build_ctx.graph.add_edge(
                child_node, parent_node, rep.Composition(index=key_str)
            )

        return parent_node

    def _build_sequence_expression(
        self, expr: ast.SeqLiteral[ast.AnyExpression]
    ) -> rep.DataNode:
        parent_node = rep.CompositeLiteral(type=extract_type_name(expr))
        self.build_ctx.graph.add_node(parent_node)

        for i, e in enumerate(expr):
            child_node = self.build_expression(e)
            self.build_ctx.graph.add_edge(
                child_node, parent_node, rep.Composition(index=str(i))
            )

        return parent_node

    def _build_scalar_literal(self, expr: ast.ScalarLiteral) -> rep.DataNode:
        location = self.build_ctx.get_location(expr)
        type_ = extract_type_name(expr)

        # FIXME: Hack
        if isinstance(expr, ast.BoolLiteral):
            lit = rep.ScalarLiteral(type=type_, value=bool(expr), location=location)
        else:
            lit = rep.ScalarLiteral(type=type_, value=expr, location=location)

        self.build_ctx.graph.add_node(lit)
        return lit

    def _build_expression(self, ast: TemplateExpressionAST) -> rep.DataNode:
        """Parse a template, add required nodes to the graph, and return the record."""
        logger.trace(f"Building expression {ast.raw!r}")

        used_variables = [
            self._resolve_variable_reference(var_name)
            for var_name in ast.referenced_variables
        ]

        en = rep.Expression(
            expr=ast.raw,
            impure_components=ast.impure_components,
            location=self.build_ctx.get_location(ast.raw),
        )
        iv = rep.IntermediateValue(identifier=self.build_ctx.next_iv_id())
        logger.trace(f"Using IV {iv!r}")
        self.build_ctx.graph.add_node(en)
        self.build_ctx.graph.add_node(iv)
        self.build_ctx.graph.add_edge(en, iv, rep.DEF)

        for var_node in used_variables:
            # Ensure the node is always added
            self.build_ctx.graph.add_node(var_node)
            self.build_ctx.graph.add_edge(var_node, en, rep.Input())

        return iv

    def _resolve_variable_reference(self, var_name: str) -> rep.Variable:
        # If the variable is initialised with an expression, this will
        # recursively evaluate the expression to give an up-to-date value.
        # However, this may cause a recursion error in case the variable is
        # self-referential.
        try:
            return self._get_variable_value(var_name)
        except RecursionError:
            raise RecursiveDefinitionError(
                f"Self-referential definition detected for {var_name!r}"
            ) from None

    def _get_variable_value(self, name: str) -> rep.Variable:
        """Get a variable value record for a variable.

        If the variable is undefined, declares a new variable.
        If the variable is defined, will return a variable and evaluate its
        initializer, if necessary.
        """
        logger.trace(f"Resolving variable {name}")
        vdef = self.build_ctx.vars.lookup_variable(name)

        if vdef is None:
            return self._get_undefined_variable_value(name)

        logger.trace(f"Found existing variable {vdef!r}")

        if isinstance(vdef.value, rep.Variable):
            return vdef.value

        # Evaluate the expression and assign it to the variable.
        value_revision = self._get_next_val_revision(vdef)
        logger.trace(
            f"Creating new value for {vdef.name!r} with value revision {value_revision}"
        )

        data_node = self.build_expression(vdef.value)
        var_node = rep.Variable(
            name=vdef.name,
            version=vdef.revision,
            value_version=value_revision,
            scope_level=vdef.env_type.value,
            prior_version=vdef.prior_version,
            location=vdef.location,
        )
        self.build_ctx.graph.add_node(var_node)
        self.build_ctx.graph.add_edge(data_node, var_node, rep.DEF)
        # Link conditions
        for cond in vdef.conditions:
            self.build_ctx.graph.add_edge(cond, var_node, rep.WHEN)
        return var_node

    def _get_undefined_variable_value(self, name: str) -> rep.Variable:
        logger.trace(f"Variable {name} has not yet been defined")
        return rep.Variable(
            name=name,
            version=0,
            value_version=0,
            scope_level=EnvironmentType.UNDEFINED.value,
        )
