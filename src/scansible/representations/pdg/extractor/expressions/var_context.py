from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager

from loguru import logger

from scansible.representations import structural as struct
from scansible.utils import SENTINEL, Sentinel

from ... import representation as rep
from .constants import PURE_FILTERS, PURE_LOOKUP_PLUGINS, PURE_TESTS
from .environments import Environment, EnvironmentStack, EnvironmentType
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


def get_nonidempotent_components(ast: TemplateExpressionAST) -> list[str]:
    comps: list[str] = []

    if ast.uses_now:
        comps.append("function 'now'")

    comps.extend(
        f"filter '{filter_op}'"
        for filter_op in ast.used_filters
        if filter_op not in PURE_FILTERS
    )
    comps.extend(
        f"test '{test_op}'" for test_op in ast.used_tests if test_op not in PURE_TESTS
    )
    comps.extend(
        f"lookup {lookup_op}"
        for lookup_op in ast.used_lookups
        if not (
            isinstance(lookup_op, LookupTargetLiteral)
            and lookup_op.name in PURE_LOOKUP_PLUGINS
        )
    )

    return comps


# TODO: Literal types
# TODO: Maybe simplify single-variable templates ("{{ var }}") to bypass
# intermediate values?
class VarContext:
    """Context for variable management."""

    def __init__(self, context: ExtractionContext) -> None:
        self._scopes = EnvironmentStack()
        self.context = context
        self._next_revnos: dict[str, int] = defaultdict(lambda: 0)
        self._next_valnos: dict[tuple[str, int], int] = {}
        self._valno_to_var: dict[tuple[str, int, int], tuple[rep.Variable, bool]] = {}

    @contextmanager
    def enter_scope(self, level: LocalEnvType) -> Generator[None, None, None]:
        self._scopes.enter_scope(level)
        yield
        self._scopes.exit_scope()

    @contextmanager
    def enter_cached_scope(self, level: LocalEnvType) -> Generator[None, None, None]:
        self._scopes.enter_cached_scope(level)
        yield
        self._scopes.exit_scope()

    def evaluate_template(self, expr: str, is_conditional: bool) -> TemplateRecord:
        """Parse a template, add required nodes to the graph, and return the record."""
        logger.debug(f"Evaluating expression {expr!r}")
        location = self.context.get_location(expr)
        ast = TemplateExpressionAST.parse(
            expr, is_conditional, self._scopes.get_variable_mapping()
        )

        if ast is None or ast.is_literal():
            logger.debug(f"{expr!r} is a literal or broken expression")
            ln = rep.Literal(value=expr, type="str", location=location)
            self.context.graph.add_node(ln)
            # Create this node purely to adhere to TemplateRecord typings so we
            # don't have to accept None as a possibility. It's never added to
            # the graph and the template record is never cached either.
            en = rep.Expression(
                expr=expr or "<empty string>", non_idempotent_components=()
            )
            return TemplateRecord(ln, en, [], True)

        used_values = self._resolve_expression_values(ast)

        non_idempotent_components = get_nonidempotent_components(ast)
        existing_tr_pair = self._scopes.get_expression(expr, used_values)
        if existing_tr_pair is None:
            logger.debug(
                f"Expression {expr!r} was (re-)evaluated, creating new expression result"
            )
            return self._create_new_expression_result(
                expr, location, used_values, non_idempotent_components
            )

        existing_tr, existing_tr_scope = existing_tr_pair
        logger.debug(
            f"Expression {expr!r} was already evaluated with the same input values, reusing previous result {existing_tr!r} from {existing_tr_scope!r}"
        )

        if non_idempotent_components:
            logger.debug(
                f"Determined that expression {expr!r} may not be idempotent, creating new expression result"
            )
            iv = rep.IntermediateValue(identifier=self.context.next_iv_id())
            logger.debug(f"Using IV {iv!r}")
            self.context.graph.add_node(iv)
            self.context.graph.add_edge(existing_tr.expr_node, iv, rep.DEF)
            return existing_tr._replace(data_node=iv)

        return existing_tr_pair[0]

    def _resolve_expression_values(
        self, ast: TemplateExpressionAST
    ) -> list[VariableValueRecord]:
        used_variables: list[VariableValueRecord] = []
        # Disable cache approximation as it's very inaccurate
        should_use_cache = False  # is_top_level and self._scopes.last_scope.is_cached

        for var_name in ast.referenced_variables:
            logger.debug(f"Resolving variable {var_name!r}")
            value_record = self._resolve_expression_value(var_name, should_use_cache)
            logger.debug(f"Determined that {ast.raw!r} uses {value_record!r}")
            used_variables.append(value_record)

        return used_variables

    def _resolve_expression_value(
        self, var_name: str, should_use_cache: bool
    ) -> VariableValueRecord:
        # Try loading from the cache if there is one we should use
        if should_use_cache:
            cached_val_record = self._scopes.current_environment.cached_results.get(
                var_name, None
            )
            if cached_val_record is not None:
                logger.debug(
                    f"Variable {var_name!r} cached in scope, reusing {cached_val_record!r}"
                )
                return cached_val_record

        # Cache miss or not using cache, get the variable value. If the variable
        # is initialised with an expression, this will recursively evaluate the
        # expression to give an up-to-date value. The value might be reused from
        # a previous evaluation.
        try:
            vr = self._get_variable_value_record(var_name)
        except RecursionError:
            raise RecursiveDefinitionError(
                f"Self-referential definition detected for {var_name!r}"
            ) from None

        # Store the variable in the cache for potential later reuse, if we need to
        if should_use_cache:
            logger.debug(f"Saving {vr!r} in cache for reuse")
            self._scopes.current_environment.cached_results[var_name] = vr

        return vr

    def _create_new_expression_result(
        self,
        expr: str,
        location: rep.NodeLocation,
        used_values: list[VariableValueRecord],
        non_idempotent_components: list[str],
    ) -> TemplateRecord:
        en = rep.Expression(
            expr=expr,
            non_idempotent_components=tuple(non_idempotent_components),
            location=location,
        )
        iv = rep.IntermediateValue(identifier=self.context.next_iv_id())
        logger.debug(f"Using IV {iv!r}")
        self.context.graph.add_node(en)
        self.context.graph.add_node(iv)
        self.context.graph.add_edge(en, iv, rep.DEF)

        def get_var_node_for_val_record(
            val_record: VariableValueRecord,
        ) -> rep.Variable:
            return self._valno_to_var[
                (val_record.name, val_record.revision, val_record.value_revision)
            ][0]

        for used_value in used_values:
            var_node = get_var_node_for_val_record(used_value)
            self.context.graph.add_edge(var_node, en, rep.USE)

        used_value_ids = [
            (vval.name, vval.revision, vval.value_revision) for vval in used_values
        ]
        tr = TemplateRecord(iv, en, used_value_ids, False)
        self._scopes.set_expression(expr, tr)
        return tr

    def add_literal(self, value: object) -> rep.Literal:
        location = self.context.get_location(value)
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

        self.context.graph.add_node(lit)
        return lit

    def register_variable(
        self, name: str, level: EnvironmentType, *, expr: Any = SENTINEL
    ) -> rep.Variable:
        """Declare a variable, initialized with the given expression.

        Expression may be empty if not available.

        Returns the newly created variable, may be added by to the graph by
        the client. If not added to the graph by the client, will be added
        when a template that uses this variable is evaluated.
        """
        logger.debug(
            f"Registering variable {name} of type {type(expr).__name__} at scope level {level.name}"
        )
        var_rev = self._next_revnos[name]
        self._next_revnos[name] += 1
        self._next_valnos[(name, var_rev)] = 0

        logger.debug(f"Selected revision {var_rev} for {name}")
        var_node = rep.Variable(
            name=name,
            version=var_rev,
            value_version=0,
            scope_level=level.value,
            location=self.context.get_location(name),
        )
        self.context.graph.add_node(var_node)

        # Store auxiliary information about which other variables are available at the
        # time this variable is registered, i.e. the ones that are "visible" to the current
        # definition.
        self.context.visibility_information.set_info(
            name, var_rev, self._scopes.get_currently_visible_definitions()
        )

        if (
            isinstance(expr, str)
            and (
                ast := TemplateExpressionAST.parse(
                    expr, False, self._scopes.get_variable_mapping()
                )
            )
            is not None
            and not ast.is_literal()
        ):
            template_expr: str | Sentinel = expr
        elif expr is SENTINEL:
            template_expr = SENTINEL
        else:
            template_expr = SENTINEL
            lit_node = self.add_literal(expr)
            self.context.graph.add_edge(lit_node, var_node, rep.DEF)

        def_record = VariableDefinitionRecord(name, var_rev, template_expr)
        self._scopes.set_variable_definition(name, def_record, level)

        # Assume the value is used by the caller is constant if they don't provide an expression.
        # Also assume the variable node we create and add here is already in use then.
        # At the very least, the caller should link it with DEF (e.g. set_fact or register)
        # or USE (e.g. undefined variables in evaluate_template).
        self._valno_to_var[(name, var_rev, 0)] = (var_node, template_expr is SENTINEL)
        if template_expr is SENTINEL:
            val_record = ConstantVariableValueRecord(def_record)
            self._scopes.set_constant_variable_value(name, val_record, level)
        # If the variable isn't a constant value, we'll only create value records whenever it's evaluated

        return var_node

    def has_variable_at_scope(self, name: str, level: EnvironmentType) -> bool:
        return any(
            scope.level is level and scope.get_variable_definition(name) is not None
            for scope in self._scopes.precedence_chain
        )

    def _create_new_variable_node(
        self, vval: VariableValueRecord, scope: Environment
    ) -> rep.Variable:
        assert (
            vval.value_revision >= 1
        ), f"Internal Error: Unacceptable value version provided"
        var_node_idx = (vval.name, vval.revision, vval.value_revision)
        old_var_node, _ = self._valno_to_var[(vval.name, vval.revision, 0)]

        new_var_node = rep.Variable(
            name=vval.name,
            version=vval.revision,
            value_version=vval.value_revision,
            scope_level=scope.level.value,
            location=self.context.get_location(vval.name),
        )
        self.context.graph.add_node(new_var_node)

        self._valno_to_var[var_node_idx] = (new_var_node, True)

        # Copy over all DEFINED_IF edges applied by the caller of this class as they should
        # apply to any new variable value revision as well. DEFINED_IF only
        # applies to definitions, not individual possible values. We'll
        # retrieve these from the first variable node, as that will be the one
        # manipulated by the caller.
        for predecessor in self.context.graph.predecessors(old_var_node):
            edge_type = self.context.graph[predecessor][old_var_node][0]["type"]
            if edge_type is not rep.DEFINED_IF:
                continue
            self.context.graph.add_edge(predecessor, new_var_node, edge_type)

        return new_var_node

    def _get_variable_value_record(self, name: str) -> VariableValueRecord:
        """Get a variable value record for a variable.

        If the variable is undefined, declares a new variable.
        If the variable is defined, will return a variable and evaluate its
        initializer, if necessary.
        """
        logger.debug(f"Resolving variable {name}")
        vdef_pair = self._scopes.get_variable_definition(name)

        # Undefined variables: Assume lowest scope
        if vdef_pair is None:
            assert (
                self._scopes.get_variable_value(name) is None
            ), f"Internal Error: Variable {name!r} has no definition but does have value"
            logger.debug(
                f"Variable {name} has not yet been defined, registering new value at lowest precedence level"
            )
            self.register_variable(name, EnvironmentType.CLI_VALUES)
            vval_pair = self._scopes.get_variable_value(name)
            assert vval_pair is not None and isinstance(
                vval_pair[0], ConstantVariableValueRecord
            ), f"Internal Error: Expected registered variable for {name!r} to be constant"
            return vval_pair[0]

        vdef, vdef_scope = vdef_pair
        expr = vdef.template_expr
        logger.debug(f"Found existing variable {vdef!r} from scope {vdef_scope!r}")

        if isinstance(expr, Sentinel):
            # No template expression, so it cannot be evaluated. There must be
            # a constant value record for it, we'll return that.
            vval_pair = self._scopes.get_variable_value(name, vdef.revision)
            assert vval_pair is not None and isinstance(
                vval_pair[0], ConstantVariableValueRecord
            ), f"Internal Error: Could not find constant value for variable without expression ({name!r})"
            logger.debug(
                f"Variable {name!r} has no initialiser, using constant value record {vval_pair[0]!r} found in {vval_pair[1]!r}"
            )
            return vval_pair[0]

        # Evaluate the expression, perhaps re-evaluating if necessary. If the
        # expression was already evaluated previously and still has the same
        # value, this will just return the previous record.
        template_record: TemplateRecord = self.evaluate_template(expr, False)

        # Try to find a pre-existing value record for this template record. If
        # it exists, we've already evaluated this variable before and we can
        # just reuse the previous one.
        vval_pair = self._scopes.get_variable_value(
            name, vdef.revision, template_record
        )
        if vval_pair is not None:
            logger.debug(
                f"Found pre-existing value {vval_pair[0]!r} originating from {vval_pair[1]!r}, reusing"
            )
            assert isinstance(
                vval_pair[0], ChangeableVariableValueRecord
            ), f"Expected evaluated value to be changeable"
            return vval_pair[0]

        # No variable value record exists yet, so we need to create a new one.
        # We'll also need to add a new variable node to the graph, although we
        # may be able to reuse the one added while registering the variable in
        # case it hasn't been used before.
        value_revision = self._next_valnos[(name, vdef.revision)]
        self._next_valnos[(name, vdef.revision)] += 1
        logger.debug(
            f"Creating new value for {name!r} with value revision {value_revision}"
        )
        value_record = ChangeableVariableValueRecord(
            vdef, value_revision, template_record
        )
        self._scopes.set_dynamic_variable_value(name, value_record)

        var_node: rep.Variable | None = None
        var_node_idx = (name, vdef.revision, value_revision)
        if var_node_idx in self._valno_to_var:
            var_node, in_use = self._valno_to_var[var_node_idx]
            if in_use:
                var_node = None
            else:
                assert (
                    var_node.version == vdef.revision
                ), "Internal Error: Bad reuse of var node, revision differs"
                assert (
                    var_node.value_version == value_revision
                ), "Internal Error: Bad reuse of var node, val revision differs"
                logger.debug(f"Using existing variable node {var_node!r}")
                # Mark as in use now.
                self._valno_to_var[var_node_idx] = (var_node, True)

        if var_node is None:
            logger.debug(f"Creating new variable node to represent value")
            var_node = self._create_new_variable_node(value_record, vdef_scope)

        # Link the edge
        self.context.graph.add_edge(template_record.data_node, var_node, rep.DEF)
        return value_record
