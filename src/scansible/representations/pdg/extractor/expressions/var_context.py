"""Logic related to variables and expression evaluation during PDG construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, final

from collections import defaultdict
from collections.abc import Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager

from ansible.module_utils.facts.system.distribution import (  # pyright: ignore[reportMissingTypeStubs]
    Distribution,
)
from loguru import logger

from scansible.representations import ast

from ... import representation as rep
from .environments import EnvironmentStack, EnvironmentType
from .environments.types import LocalEnvType
from .expression_types import extract_type_name
from .records import VariableDefinitionRecord
from .templates import TemplateExpressionAST

if TYPE_CHECKING:
    from ..context import ExtractionContext


class RecursiveDefinitionError(Exception):
    pass


_DefRevisionMap = dict[str, int]
_ValRevisionMap = dict[VariableDefinitionRecord, int]


# TODO: Maybe simplify single-variable templates ("{{ var }}") to bypass
# intermediate values?
@final
class VarContext:
    """Context for variable management."""

    def __init__(self, context: ExtractionContext) -> None:
        self._envs = EnvironmentStack()
        self.extraction_ctx = context
        self._next_def_revisions: _DefRevisionMap = defaultdict(lambda: 0)
        self._next_val_revisions: _ValRevisionMap = defaultdict(lambda: 0)

    def _get_next_def_revision(self, var_name: str) -> int:
        self._next_def_revisions[var_name] += 1
        return self._next_def_revisions[var_name] - 1

    def _get_next_val_revision(self, var_def: VariableDefinitionRecord) -> int:
        self._next_val_revisions[var_def] += 1
        return self._next_val_revisions[var_def] - 1

    @contextmanager
    def enter_scope(self, env_type: LocalEnvType) -> Generator[None]:
        self._envs.enter_scope(env_type)
        yield
        self._envs.exit_scope()

    def build_expression(self, expr: ast.AnyExpression) -> rep.DataNode:
        if isinstance(expr, ast.Expression):
            return self._build_expression(TemplateExpressionAST(expr))
        if isinstance(expr, ast.SeqLiteral):
            return self._build_sequence_expression(expr)
        elif isinstance(expr, ast.MapLiteral):
            return self._build_mapping_expression(expr)
        else:
            return self._build_scalar_literal(expr)

    def _build_mapping_expression(
        self, expr: ast.MapLiteral[ast.ScalarLiteral, ast.AnyExpression]
    ) -> rep.DataNode:
        parent_node = rep.CompositeLiteral(type=extract_type_name(expr))
        self.extraction_ctx.graph.add_node(parent_node)

        for k, v in expr.items():
            child_node = self.build_expression(v)
            key_str = str(k)
            self.extraction_ctx.graph.add_edge(
                child_node, parent_node, rep.Composition(index=key_str)
            )

        return parent_node

    def _build_sequence_expression(
        self, expr: ast.SeqLiteral[ast.AnyExpression]
    ) -> rep.DataNode:
        parent_node = rep.CompositeLiteral(type=extract_type_name(expr))
        self.extraction_ctx.graph.add_node(parent_node)

        for i, e in enumerate(expr):
            child_node = self.build_expression(e)
            self.extraction_ctx.graph.add_edge(
                child_node, parent_node, rep.Composition(index=str(i))
            )

        return parent_node

    def _build_scalar_literal(self, expr: ast.ScalarLiteral) -> rep.DataNode:
        location = self.extraction_ctx.get_location(expr)
        type_ = extract_type_name(expr)

        # FIXME: Hack
        if isinstance(expr, ast.BoolLiteral):
            lit = rep.ScalarLiteral(type=type_, value=bool(expr), location=location)
        else:
            lit = rep.ScalarLiteral(type=type_, value=expr, location=location)

        self.extraction_ctx.graph.add_node(lit)
        return lit

    def _build_expression(self, ast: TemplateExpressionAST) -> rep.DataNode:
        """Parse a template, add required nodes to the graph, and return the record."""
        logger.debug(f"Building expression {ast.raw!r}")

        used_variables = [
            self._resolve_variable_reference(var_name)
            for var_name in ast.referenced_variables
        ]

        en = rep.Expression(
            expr=ast.raw,
            impure_components=ast.impure_components,
            location=self.extraction_ctx.get_location(ast.raw),
        )
        iv = rep.IntermediateValue(identifier=self.extraction_ctx.next_iv_id())
        logger.debug(f"Using IV {iv!r}")
        self.extraction_ctx.graph.add_node(en)
        self.extraction_ctx.graph.add_node(iv)
        self.extraction_ctx.graph.add_edge(en, iv, rep.DEF)

        for var_node in used_variables:
            # Ensure the node is always added
            self.extraction_ctx.graph.add_node(var_node)
            self.extraction_ctx.graph.add_edge(var_node, en, rep.Input())

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

    def define_lazy_variable(
        self,
        name: ast.Identifier,
        env_type: EnvironmentType,
        initialiser: ast.AnyExpression,
        *,
        conditions: Sequence[rep.DataNode] | None = None,
    ) -> None:
        """Define a variable with an initialiser which is lazily evaluated.

        The variable node will be added to the graph on-demand when dereferenced.
        """
        revision = self._get_next_def_revision(name)
        logger.debug(f"Selected revision {revision} for {name}")
        self._define_variable(name, revision, env_type, initialiser, conditions)

    def define_eager_variable(
        self,
        name: str,
        env_type: EnvironmentType,
        *,
        conditions: Sequence[rep.DataNode] | None = None,
    ) -> rep.Variable:
        """Define a variable whose value is already eagerly evaluated.

        Callers are responsible for linking the defining node, if any.
        """
        revision = self._get_next_def_revision(name)
        logger.debug(f"Selected revision {revision} for {name}")
        var_node = rep.Variable(
            name=name,
            version=revision,
            value_version=0,
            scope_level=env_type.value,
            location=self.extraction_ctx.get_location(name),
        )
        self.extraction_ctx.graph.add_node(var_node)
        for cond in conditions or []:
            self.extraction_ctx.graph.add_edge(cond, var_node, rep.WHEN)
        self._define_variable(name, revision, env_type, var_node, conditions)
        return var_node

    def _define_variable(
        self,
        name: str,
        revision: int,
        env_type: EnvironmentType,
        value: ast.AnyExpression | rep.Variable,
        conditions: Sequence[rep.DataNode] | None,
    ) -> None:
        """Declare a variable, bound to the given value.

        The value is either an actual variable node, in case the variable is injected with an eagerly-evaluated
        value, or an expression to be lazily evaluated when the variable is dereferenced.
        """
        logger.debug(f"Defining variable {name!r} in env of type {env_type.name}")

        # Store auxiliary information about which other variables are available
        # at the time this variable is registered, i.e. the ones that are
        # "visible" to the current definition.
        self.extraction_ctx.visibility_information.set_info(
            name, revision, self._envs.get_currently_visible_definitions()
        )

        def_record = VariableDefinitionRecord(
            name,
            revision,
            value,
            env_type,
            tuple(conditions or []),
            self.extraction_ctx.get_location(name),
        )
        self._envs.set_variable_definition(def_record)

    def _get_variable_value(self, name: str) -> rep.Variable:
        """Get a variable value record for a variable.

        If the variable is undefined, declares a new variable.
        If the variable is defined, will return a variable and evaluate its
        initializer, if necessary.
        """
        logger.debug(f"Resolving variable {name}")
        vdef = self._envs.get_variable_definition(name)

        if vdef is None:
            return self._get_undefined_variable_value(name)

        logger.debug(f"Found existing variable {vdef!r}")

        if isinstance(vdef.value, rep.Variable):
            return vdef.value

        # Evaluate the expression and assign it to the variable.
        value_revision = self._get_next_val_revision(vdef)
        logger.debug(
            f"Creating new value for {vdef.name!r} with value revision {value_revision}"
        )

        data_node = self.build_expression(vdef.value)
        var_node = rep.Variable(
            name=vdef.name,
            version=vdef.revision,
            value_version=value_revision,
            scope_level=vdef.env_type.value,
            location=vdef.location,
        )
        self.extraction_ctx.graph.add_node(var_node)
        self.extraction_ctx.graph.add_edge(data_node, var_node, rep.DEF)
        # Link conditions
        for cond in vdef.conditions:
            self.extraction_ctx.graph.add_edge(cond, var_node, rep.WHEN)
        return var_node

    def _get_undefined_variable_value(self, name: str) -> rep.Variable:
        logger.debug(f"Variable {name} has not yet been defined")
        return rep.Variable(
            name=name,
            version=0,
            value_version=0,
            scope_level=EnvironmentType.UNDEFINED.value,
        )

    def get_initialisers(
        self, name: str, constraints: Mapping[str, ast.AnyExpression]
    ) -> Sequence[
        tuple[
            ast.AnyExpression, Mapping[str, ast.AnyExpression], Sequence[ast.Condition]
        ]
    ]:
        """Get possible initialisers for `name`, adhering to any prior
        initialiser constraints.
        Returns tuples of initialisers, new constraints, and new conditions."""
        # If we already resolved this var to an initialiser before, reuse the
        # same initialiser.
        if name in constraints:
            return [(constraints[name], {}, [])]

        # TODO: Conditional definitions.
        vdef = self._envs.get_variable_definition(name)

        if vdef is None or vdef.env_type in (
            EnvironmentType.MAGIC_VARS,
            EnvironmentType.HOST_FACTS,
        ):
            return [
                (init, {name: init}, conditions)
                for init, conditions in self._get_constrained_magic_initialisers(
                    name, constraints
                )
            ]

        if not isinstance(vdef.value, rep.Variable):
            return [(vdef.value, {name: vdef.value}, [])]

        return []

    def _get_constrained_magic_initialisers(
        self, name: str, constraints: Mapping[str, ast.AnyExpression]
    ) -> Sequence[tuple[ast.StrLiteral, Sequence[ast.Condition]]]:
        if name not in ("ansible_os_family", "ansible_distribution"):
            return []

        values: Iterable[str]
        os_family_map = Distribution.OS_FAMILY_MAP
        os_family = cast(dict[str, str], Distribution.OS_FAMILY)
        if name == "ansible_os_family":
            distribution_constraint = constraints.get("ansible_distribution")
            if distribution_constraint and isinstance(distribution_constraint, str):
                values = [os_family[distribution_constraint]]
            else:
                values = os_family_map.keys()
        elif name == "ansible_distribution":
            os_family_constraint = constraints.get("ansible_os_family")
            if os_family_constraint and isinstance(os_family_constraint, str):
                values = os_family_map[os_family_constraint]
            else:
                values = os_family.keys()

        values = [ast.StrLiteral(value) for value in values]

        return [
            (value, [ast.Condition.model_validate(f'{name} == "{value}"')])
            for value in values
        ]
