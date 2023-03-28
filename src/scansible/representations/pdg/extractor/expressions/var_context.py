from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, cast

from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager

from loguru import logger

from scansible.representations import structural as struct
from scansible.utils import SENTINEL, Sentinel, first
from scansible.utils.type_validators import ensure_not_none

from ... import representation as rep
from .constants import PURE_FILTERS, PURE_LOOKUP_PLUGINS, PURE_TESTS
from .environments import EnvironmentStack, EnvironmentType
from .environments.types import LocalEnvType
from .records import (
    ChangeableVariableValueRecord,
    ConstantVariableValueRecord,
    TemplateRecord,
    VariableDefinitionRecord,
    VariableValueRecord,
)

if TYPE_CHECKING:
    from ..context import ExtractionContext

from .templates import LookupTargetLiteral, TemplateExpressionAST


class RecursiveDefinitionError(Exception):
    pass


def _get_impure_components(ast: TemplateExpressionAST) -> Iterable[str]:
    if ast.uses_now:
        yield "function 'now'"

    yield from (
        f"filter '{filter_op}'"
        for filter_op in ast.used_filters
        if filter_op not in PURE_FILTERS
    )
    yield from (
        f"test '{test_op}'" for test_op in ast.used_tests if test_op not in PURE_TESTS
    )
    yield from (
        f"lookup {lookup_op}"
        for lookup_op in ast.used_lookups
        if not (
            isinstance(lookup_op, LookupTargetLiteral)
            and lookup_op.name in PURE_LOOKUP_PLUGINS
        )
    )


def _is_impure_expression(ast: TemplateExpressionAST) -> bool:
    return first(_get_impure_components(ast)) is not None


_DefRevisionMap = dict[str, int]
_ValRevisionMap = dict[VariableDefinitionRecord, int]
_ValueToVarMap = dict[tuple[VariableDefinitionRecord, int], rep.Variable]


# TODO: Composite literals
# TODO: Maybe simplify single-variable templates ("{{ var }}") to bypass
# intermediate values?
class VarContext:
    """Context for variable management."""

    def __init__(self, context: ExtractionContext) -> None:
        self._envs = EnvironmentStack()
        self.extraction_ctx = context
        self._next_def_revisions: _DefRevisionMap = defaultdict(lambda: 0)
        self._next_val_revisions: _ValRevisionMap = defaultdict(lambda: 0)
        self._value_to_var_node: _ValueToVarMap = {}

    def _get_next_def_revision(self, var_name: str) -> int:
        self._next_def_revisions[var_name] += 1
        return self._next_def_revisions[var_name] - 1

    def _get_next_val_revision(self, var_def: VariableDefinitionRecord) -> int:
        self._next_val_revisions[var_def] += 1
        return self._next_val_revisions[var_def] - 1

    def _get_var_node_for_value(
        self,
        var_def: VariableDefinitionRecord,
        val_revision: int,
        *,
        allow_undefined: bool = True,
    ) -> rep.Variable:
        var_node = self._value_to_var_node.get((var_def, val_revision))
        assert (
            allow_undefined or var_node is not None
        ), "Internal error: var node undefined"

        if var_node is None:
            assert val_revision > 0, "Internal error: First variable node undefined"
            logger.debug(f"Creating new variable node to represent value")
            old_var_node = self._get_var_node_for_value(
                var_def, 0, allow_undefined=False
            )

            var_node = rep.Variable(
                name=var_def.name,
                version=var_def.revision,
                value_version=val_revision,
                scope_level=var_def.env_type.value,
                location=old_var_node.location,
            )

            self.extraction_ctx.graph.add_node(var_node)
            self._value_to_var_node[(var_def, val_revision)] = var_node
            self._copy_cond_edges(old_var_node, var_node)
        else:
            logger.debug(f"Using existing variable node {var_node!r}")

        return var_node

    def _copy_cond_edges(
        self, old_var_node: rep.Variable, new_var_node: rep.Variable
    ) -> None:
        # TODO: Change this once VarContext stores the conditions itself.
        # Copy over all DEFINED_IF edges applied by the caller of this class as they should
        # apply to any new variable value revision as well. DEFINED_IF only
        # applies to definitions, not individual possible values. We'll
        # retrieve these from the first variable node, as that will be the one
        # manipulated by the caller.
        for predecessor in self.extraction_ctx.graph.predecessors(old_var_node):
            edge_type = self.extraction_ctx.graph[predecessor][old_var_node][0]["type"]
            if edge_type is not rep.DEFINED_IF:
                continue
            self.extraction_ctx.graph.add_edge(predecessor, new_var_node, edge_type)

    @contextmanager
    def enter_scope(self, env_type: LocalEnvType) -> Generator[None, None, None]:
        self._envs.enter_scope(env_type)
        yield
        self._envs.exit_scope()

    @contextmanager
    def enter_cached_scope(self, env_type: LocalEnvType) -> Generator[None, None, None]:
        self._envs.enter_cached_scope(env_type)
        yield
        self._envs.exit_scope()

    def build_expression(self, expr: struct.AnyValue) -> rep.DataNode:
        return self._build_expression(expr, is_conditional=False)

    def build_conditional_expression(self, expr: struct.AnyValue) -> rep.DataNode:
        return self._build_expression(expr, is_conditional=True)

    def _build_expression(
        self, expr: struct.AnyValue, is_conditional: bool
    ) -> rep.DataNode:
        if not isinstance(expr, str):
            return self._add_literal_node(expr)

        if is_conditional:
            ast = TemplateExpressionAST.parse_conditional(
                expr, self._envs.get_variable_initialisers()
            )
        else:
            ast = TemplateExpressionAST.parse(expr)

        if ast is None or ast.is_literal():
            if ast is None:
                logger.warning(f"{expr!r} is malformed")
            logger.debug(f"{expr!r} is a literal or malformed expression")
            return self._add_literal_node(expr)

        return self._resolve_expression(ast).data_node

    def _add_literal_node(self, value: object) -> rep.Literal:
        location = self.extraction_ctx.get_location(value)
        type_ = cast(rep.ValidTypeStr, value.__class__.__name__)
        type_mappings: dict[str, rep.ValidTypeStr] = {
            "AnsibleUnicode": "str",
            "AnsibleSequence": "list",
            "AnsibleMapping": "dict",
            "AnsibleUnsafeText": "str",
        }
        type_ = type_mappings.get(type_, type_)
        if isinstance(value, (dict, list)):
            logger.warning("I am not able to handle composite literals yet")
            lit = rep.Literal(
                type=type_,
                value=str(value),  # pyright: ignore
                location=location,
            )
        elif isinstance(value, struct.VaultValue):
            lit = rep.Literal(type=type_, value=str(value), location=location)
        else:
            lit = rep.Literal(type=type_, value=value, location=location)

        self.extraction_ctx.graph.add_node(lit)
        return lit

    def _resolve_expression(self, ast: TemplateExpressionAST) -> TemplateRecord:
        """Parse a template, add required nodes to the graph, and return the record."""
        logger.debug(f"Building expression {ast.raw!r}")
        assert not ast.is_literal(), f"Expected an expression, got literal {ast.raw!r}"

        used_values = list(self._resolve_expression_values(ast))

        tr = self._envs.get_expression_evaluation_result(ast.raw, used_values)
        if tr is None:
            logger.debug(f"First evaluation of expression {ast.raw!r} in this context")
            return self._create_new_expression_result(ast, used_values)

        logger.debug(f"Re-evaluation of {tr!r} for expression {ast.raw!r}")
        if _is_impure_expression(ast):
            logger.debug(f"Expression {ast.raw!r} may be impure, creating new result")
            return self._create_reevaluated_impure_expression_result(tr)

        logger.debug(f"Expression {ast.raw!r} is pure, reusing prior evaluation")
        return tr

    def _resolve_expression_values(
        self, ast: TemplateExpressionAST
    ) -> Iterable[VariableValueRecord]:
        # Disable cache approximation as it's very inaccurate
        should_use_cache = False  # is_top_level and self._scopes.last_scope.is_cached

        for var_name in ast.referenced_variables:
            logger.debug(f"Resolving variable {var_name!r}")
            value_record = self._resolve_expression_value(var_name, should_use_cache)
            logger.debug(f"Determined that {ast.raw!r} uses {value_record!r}")
            yield value_record

    def _resolve_expression_value(
        self, var_name: str, should_use_cache: bool
    ) -> VariableValueRecord:
        if should_use_cache:
            return self._resolve_expression_cached_value(var_name)
        else:
            return self._resolve_expression_uncached_value(var_name)

    def _resolve_expression_uncached_value(self, var_name: str) -> VariableValueRecord:
        # If the variable is initialised with an expression, this will
        # recursively evaluate the expression to give an up-to-date value.
        # The value might be reused from a previous evaluation.
        try:
            return self._get_variable_value_record(var_name)
        except RecursionError:
            raise RecursiveDefinitionError(
                f"Self-referential definition detected for {var_name!r}"
            ) from None

    def _resolve_expression_cached_value(self, var_name: str) -> VariableValueRecord:
        # Try loading from the cache
        vr = self._envs.top_environment.cached_results.get(var_name, None)
        if vr is not None:
            logger.debug(f"Variable {var_name!r} cached in current env, reusing {vr!r}")
            return vr

        # Cache miss, proceed as normal
        vr = self._resolve_expression_uncached_value(var_name)

        # Store the variable in the cache for potential later reuse
        logger.debug(f"Saving {vr!r} in cache for reuse")
        self._envs.top_environment.cached_results[var_name] = vr

        return vr

    def _create_new_expression_result(
        self, ast: TemplateExpressionAST, used_values: list[VariableValueRecord]
    ) -> TemplateRecord:
        en = rep.Expression(
            expr=ast.raw,
            impure_components=tuple(_get_impure_components(ast)),
            location=self.extraction_ctx.get_location(ast.raw),
        )
        iv = rep.IntermediateValue(identifier=self.extraction_ctx.next_iv_id())
        logger.debug(f"Using IV {iv!r}")
        self.extraction_ctx.graph.add_node(en)
        self.extraction_ctx.graph.add_node(iv)
        self.extraction_ctx.graph.add_edge(en, iv, rep.DEF)

        for used_value in used_values:
            var_node = self._get_var_node_for_value(
                used_value.variable_definition,
                used_value.value_revision,
                allow_undefined=False,
            )
            self.extraction_ctx.graph.add_edge(var_node, en, rep.USE)

        tr = TemplateRecord(iv, en, used_values, False)
        self._envs.set_expression_evaluation_result(ast.raw, tr)
        return tr

    def _create_reevaluated_impure_expression_result(
        self, tr: TemplateRecord
    ) -> TemplateRecord:
        iv = rep.IntermediateValue(identifier=self.extraction_ctx.next_iv_id())
        logger.debug(f"Using IV {iv!r}")

        self.extraction_ctx.graph.add_node(iv)
        self.extraction_ctx.graph.add_edge(tr.expr_node, iv, rep.DEF)
        return tr.__replace__(data_node=iv)  # type: ignore[return-value]

    def _is_template(self, expr: struct.AnyValue | Sentinel) -> bool:
        return (
            isinstance(expr, str)
            and (ast := TemplateExpressionAST.parse(expr)) is not None
            and not ast.is_literal()
        )

    def define_variable(
        self,
        name: str,
        env_type: EnvironmentType,
        *,
        expr: struct.AnyValue | Sentinel = SENTINEL,
    ) -> rep.Variable:
        """Declare a variable, initialized with the given expression.

        Expression may be empty if not available.

        Returns the newly created variable, may be added by to the graph by
        the client. If not added to the graph by the client, will be added
        when a template that uses this variable is evaluated.
        """
        logger.debug(
            f"Defining variable {name!r} of type {type(expr).__name__} "
            + f"in env of type {env_type.name}"
        )

        var_rev = self._get_next_def_revision(name)
        logger.debug(f"Selected revision {var_rev} for {name}")
        var_node = rep.Variable(
            name=name,
            version=var_rev,
            value_version=0,
            scope_level=env_type.value,
            location=self.extraction_ctx.get_location(name),
        )
        self.extraction_ctx.graph.add_node(var_node)

        # Store auxiliary information about which other variables are available
        # at the time this variable is registered, i.e. the ones that are
        # "visible" to the current definition.
        self.extraction_ctx.visibility_information.set_info(
            name, var_rev, self._envs.get_currently_visible_definitions()
        )

        if self._is_template(expr):
            assert isinstance(expr, str)
            template_expr: str | Sentinel = expr
        elif expr is SENTINEL:
            template_expr = SENTINEL
        else:
            template_expr = SENTINEL
            lit_node = self._add_literal_node(expr)
            self.extraction_ctx.graph.add_edge(lit_node, var_node, rep.DEF)

        def_record = VariableDefinitionRecord(name, var_rev, template_expr, env_type)
        self._envs.set_variable_definition(name, def_record)
        self._value_to_var_node[(def_record, 0)] = var_node

        # Assume the value is used by the caller is constant if they don't
        # provide an expression. At the very least, the caller should link it
        # with DEF (e.g. set_fact or register) or USE (e.g. undefined variables
        # in evaluate_template).
        # If the variable isn't a constant value, we'll only create value
        # records whenever it's evaluated.
        if template_expr is SENTINEL:
            val_record = ConstantVariableValueRecord(def_record)
            self._envs.set_constant_variable_value(name, val_record)

        return var_node

    def _get_variable_value_record(self, name: str) -> VariableValueRecord:
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
        if isinstance(vdef.template_expr, Sentinel):
            return self._get_variable_value_without_initialiser(vdef)

        # Evaluate the expression, perhaps re-evaluating if necessary. If the
        # expression was already evaluated previously and still has the same
        # value, this will just return the previous record.
        ast = ensure_not_none(TemplateExpressionAST.parse(vdef.template_expr))
        template_record = self._resolve_expression(ast)

        # Try to find a pre-existing value record for this template record. If
        # it exists, we've already evaluated this variable before and we can
        # just reuse the previous one.
        vval = self._envs.get_variable_value_for_cached_expression(
            name, vdef.revision, template_record
        )
        if vval is None:
            return self._create_new_variable_value(vdef, template_record)

        logger.debug(f"Found pre-existing value {vval!r}, reusing")
        assert isinstance(
            vval, ChangeableVariableValueRecord
        ), f"Expected evaluated value to be changeable"
        return vval

    def _create_new_variable_value(
        self, vdef: VariableDefinitionRecord, template_record: TemplateRecord
    ) -> VariableValueRecord:
        # No variable value record exists yet, so we need to create a new one.
        # We'll also need to add a new variable node to the graph, although we
        # may be able to reuse the one added while registering the variable in
        # case it hasn't been used before.
        value_revision = self._get_next_val_revision(vdef)
        logger.debug(
            f"Creating new value for {vdef.name!r} with value revision {value_revision}"
        )
        value_record = ChangeableVariableValueRecord(
            vdef, value_revision, template_record
        )
        self._envs.set_changeable_variable_value(vdef.name, value_record)

        var_node = self._get_var_node_for_value(vdef, value_revision)
        assert (
            var_node.version == vdef.revision
        ), "Internal Error: Bad reuse of var node, revision differs"
        assert (
            var_node.value_version == value_revision
        ), "Internal Error: Bad reuse of var node, val revision differs"

        # Link the edge
        self.extraction_ctx.graph.add_edge(template_record.data_node, var_node, rep.DEF)
        return value_record

    def _get_undefined_variable_value(self, name: str) -> ConstantVariableValueRecord:
        assert not self._envs.has_variable_value(
            name
        ), f"Internal Error: Variable {name!r} has no definition but does have value"
        logger.debug(
            f"Variable {name} has not yet been defined, "
            + "registering new value at lowest precedence level"
        )

        # Undefined variables: Assume lowest scope
        self.define_variable(name, EnvironmentType.UNDEFINED)
        vval = self._envs.get_variable_value(name)
        assert vval is not None and isinstance(
            vval, ConstantVariableValueRecord
        ), f"Internal Error: Expected registered variable for {name!r} to be constant"
        return vval

    def _get_variable_value_without_initialiser(
        self, vdef: VariableDefinitionRecord
    ) -> ConstantVariableValueRecord:
        # No template expression, so it cannot be evaluated. There must be
        # a constant value record for it, we'll return that.
        vval = self._envs.get_variable_value_for_constant_definition(
            vdef.name, vdef.revision
        )
        assert vval is not None and isinstance(
            vval, ConstantVariableValueRecord
        ), f"Internal Error: Could not find constant value for variable without expression ({vdef.name!r})"
        logger.debug(
            f"Variable {vdef.name!r} has no initialiser, using constant value record {vval!r}"
        )
        return vval
