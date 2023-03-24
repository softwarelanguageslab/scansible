from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Literal as LiteralT
from typing import NamedTuple, cast, overload

from collections import defaultdict
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from enum import Enum

from loguru import logger

from scansible.representations import structural as struct
from scansible.utils import SENTINEL, Sentinel
from scansible.utils.type_validators import ensure_not_none

from ... import representation as rep
from .constants import PURE_FILTERS, PURE_LOOKUP_PLUGINS, PURE_TESTS

if TYPE_CHECKING:
    from ..context import ExtractionContext

from .templates import LookupTargetLiteral, TemplateExpressionAST


class TemplateRecord(NamedTuple):
    """State of a template expression."""

    data_node: rep.DataNode
    expr_node: rep.Expression
    used_variables: list[tuple[str, int, int]]
    is_literal: bool

    @property
    def may_be_dynamic(self) -> bool:
        return not self.expr_node.idempotent

    def __repr__(self) -> str:
        return f"TemplateRecord(expr={self.expr_node.expr!r}, data_node={self.data_node.node_id}, expr_node={self.expr_node.node_id})"


class VariableDefinitionRecord(NamedTuple):
    """Binding of a variable at any given time."""

    name: str
    revision: int
    template_expr: str | Sentinel

    def __repr__(self) -> str:
        return f"VariableDefinitionRecord(name={self.name!r}, revision={self.revision}, expr={self.template_expr!r})"


class VariableValueRecord:
    """Binding of a variable at any given time."""

    def __init__(self, var_def: VariableDefinitionRecord, val_revision: int) -> None:
        self.var_def = var_def
        self.val_revision = val_revision

    @property
    def name(self) -> str:
        return self.var_def.name

    @property
    def revision(self) -> int:
        return self.var_def.revision

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(var_def={self.var_def!r}, val_revision={self.val_revision})"


class ConstantVariableValueRecord(VariableValueRecord):
    def copy(self) -> ConstantVariableValueRecord:
        return ConstantVariableValueRecord(self.var_def, self.val_revision)


class ChangeableVariableValueRecord(VariableValueRecord):
    def __init__(
        self,
        var_def: VariableDefinitionRecord,
        val_revision: int,
        template_record: TemplateRecord,
    ) -> None:
        super().__init__(var_def, val_revision)
        self.template_record = template_record

    def copy(self) -> ChangeableVariableValueRecord:
        return ChangeableVariableValueRecord(
            self.var_def, self.val_revision, self.template_record
        )


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


class RecursiveDefinitionError(Exception):
    pass


class Scope:
    def __init__(self, level: ScopeLevel, is_cached: bool = False) -> None:
        self.level = level
        self.is_cached = is_cached
        self.cached_results: dict[str, VariableValueRecord] = {}
        # Values of expressions valid in this scope
        self._expr_store: dict[str, TemplateRecord] = {}
        # Variables defined in this scope
        self._var_def_store: dict[str, VariableDefinitionRecord] = {}
        # Values of variables in this scope. Variable itself can come from an
        # outer scope, but its value may depend on variables defined within
        # this scope
        self._var_val_store: dict[str, VariableValueRecord] = {}

    def __repr__(self) -> str:
        return f"Scope(level={self.level.name}, is_cached={self.is_cached})"

    def get_variable_definition(self, name: str) -> VariableDefinitionRecord | None:
        return self._var_def_store.get(name)

    def set_variable_definition(self, name: str, rec: VariableDefinitionRecord) -> None:
        self._var_def_store[name] = rec

    def has_variable_definition(self, name: str, revision: int) -> bool:
        return (
            name in self._var_def_store
            and self._var_def_store[name].revision == revision
        )

    def get_variable_value(self, name: str) -> VariableValueRecord | None:
        return self._var_val_store.get(name)

    def set_variable_value(self, name: str, rec: VariableValueRecord) -> None:
        self._var_val_store[name] = rec

    def has_variable_value(self, name: str, def_rev: int, val_rev: int) -> bool:
        return (
            name in self._var_val_store
            and self._var_val_store[name].revision == def_rev
            and self._var_val_store[name].val_revision == val_rev
        )

    def get_var_mapping(self) -> dict[str, str]:
        return {
            vr.name: vr.template_expr
            for vr in self._var_def_store.values()
            if not isinstance(vr.template_expr, Sentinel)
        }

    def get_all_defined_variables(self) -> dict[str, int]:
        return {vr.name: vr.revision for vr in self._var_def_store.values()}

    def get_expression(self, expr: str) -> TemplateRecord | None:
        return self._expr_store.get(expr)

    def set_expression(self, expr: str, rec: TemplateRecord) -> None:
        self._expr_store[expr] = rec

    def has_expression(self, expr: str) -> bool:
        return expr in self._expr_store

    def __str__(self) -> str:
        out = "Scope@" + self.level.name
        locals_str = (
            ", ".join(f"{v.name}@{v.revision}" for v in self._var_def_store.values())
            or "none"
        )
        values_str = (
            ", ".join(
                f"{v.name}@{v.revision}.{v.val_revision}"
                for v in self._var_val_store.values()
            )
            or "none"
        )
        exprs_str = (
            ", ".join(
                e.expr_node.expr + (" (dynamic)" if e.may_be_dynamic else "")
                for e in self._expr_store.values()
                if not e.is_literal
            )
            or "none"
        )
        return f"{out} (locals: {locals_str}, values: {values_str}, expressions: {exprs_str})"


class ScopeLevel(Enum):
    """Possible scope levels.

    Element's value is the precedence level, higher wins.
    "Virtual" scope levels have a negative precedence. Virtual scope levels
    don't exist in Ansible, but are used internally to determine variable
    placement.
    """

    CLI_VALUES = 0
    ROLE_DEFAULTS = 1
    INV_FILE_GROUP_VARS = 2
    INV_GROUP_VARS_ALL = 3
    PB_GROUP_VARS_ALL = 4
    INV_GROUP_VARS = 5
    PB_GROUP_VARS = 6
    INV_FILE_HOST_VARS = 7
    INV_HOST_VARS = 8
    PB_HOST_VARS = 9
    HOST_FACTS = 10
    PLAY_VARS = 11
    PLAY_VARS_PROMPT = 12
    PLAY_VARS_FILES = 13
    ROLE_VARS = 14
    BLOCK_VARS = 15
    TASK_VARS = 16
    INCLUDE_VARS = 17
    SET_FACTS_REGISTERED = 18  # set_fact and register
    ROLE_PARAMS = 19
    INCLUDE_PARAMS = 20
    EXTRA_VARS = 21

    OF_TEMPLATE = -1
    CURRENT_SCOPE = -2


"""Scopes which can be stacked, i.e., for which a new scope can be created."""
STACKABLE_SCOPES = {
    ScopeLevel.ROLE_DEFAULTS,
    ScopeLevel.ROLE_VARS,  # TODO: Do these pop when the role is left?
    ScopeLevel.TASK_VARS,
    ScopeLevel.BLOCK_VARS,
    ScopeLevel.ROLE_PARAMS,
    ScopeLevel.INCLUDE_PARAMS,
}


def values_have_changed(
    tr: TemplateRecord, used_values: list[VariableValueRecord]
) -> bool:
    logger.debug(f"Checking whether dependences of {tr!r} match desired state")
    prev_used = sorted(tr.used_variables, key=lambda uv: uv[0])
    curr_used = sorted(
        [(uv.name, uv.revision, uv.val_revision) for uv in used_values],
        key=lambda uv: uv[0],
    )

    if len(prev_used) != len(curr_used):
        logger.debug(
            "Previous and current use different number of variables. DECISION: CHANGED"
        )
        return True
    # Pairwise check. We could arguably just do prev_used == curr_used but we want informative debug logs
    for prev, curr in zip(prev_used, curr_used):
        if prev != curr:
            pname, prevision, pval = prev
            cname, crevision, cval = curr
            logger.debug(
                f"Previous uses {pname}@{prevision}.{pval}, current uses {cname}@{crevision}.{cval}. DECISION: CHANGED"
            )
            return True

    logger.debug(f"No differences in used variables found. DECISION: UNCHANGED")
    return False


class ScopeContext:
    """Collection of variable scopes."""

    def __init__(self) -> None:
        self._scope_stack: list[Scope] = []
        for level in sorted(
            set(ScopeLevel) - STACKABLE_SCOPES, key=lambda level: level.value
        ):
            if level.value < 0:
                continue
            self._scope_stack.append(Scope(level))

    @property
    def precedence_chain(self) -> Iterable[Scope]:
        return self._calculate_precedence_chain(self._scope_stack)

    def _calculate_precedence_chain(self, scope_stack: list[Scope]) -> Iterable[Scope]:
        return sorted(scope_stack, key=lambda scope: scope.level.value)[::-1]

    @property
    def last_scope(self) -> Scope:
        return self._scope_stack[-1]

    @overload
    def _get_most_specific(
        self, key: str, type: LiteralT["variable_value"]
    ) -> tuple[VariableValueRecord, Scope] | None:
        """See non-overloaded variant."""
        ...

    @overload
    def _get_most_specific(
        self, key: str, type: LiteralT["variable_definition"]
    ) -> tuple[VariableDefinitionRecord, Scope] | None:
        """See non-overloaded variant."""
        ...

    @overload
    def _get_most_specific(
        self, key: str, type: LiteralT["expression"]
    ) -> tuple[TemplateRecord, Scope] | None:
        ...

    def _get_most_specific(
        self,
        key: str,
        type: LiteralT["variable_value", "variable_definition", "expression"],
    ) -> (
        tuple[VariableValueRecord | VariableDefinitionRecord | TemplateRecord, Scope]
        | None
    ):
        return next(
            (
                (rec, scope)
                for scope in self.precedence_chain
                if (rec := getattr(scope, f"get_{type}")(key)) is not None
            ),
            None,
        )

    def get_variable_value(
        self,
        name: str,
        revision: int = -1,
        template_record: TemplateRecord | None = None,
    ) -> tuple[VariableValueRecord, Scope] | None:
        for scope in self._scope_stack[::-1]:
            possible_vval = scope.get_variable_value(name)
            if possible_vval is None:
                continue

            logger.debug(f"Found possible value for {name!r}: {possible_vval!r}")
            if revision >= 0 and possible_vval.revision != revision:
                logger.debug("Ignoring: Wrong definition version")
                continue

            is_correct_type = (template_record is None) == isinstance(
                possible_vval, ConstantVariableValueRecord
            )
            if not is_correct_type:
                logger.debug("Ignoring: Wrong type for request")
                continue

            if template_record is None:
                logger.debug("Hit!")
                return possible_vval, scope

            assert isinstance(possible_vval, ChangeableVariableValueRecord)
            if possible_vval.template_record != template_record:
                logger.debug(
                    f"Ignoring: Wrong template record: {possible_vval.template_record!r} vs {template_record!r}"
                )
                continue

            logger.debug("Hit!")
            return possible_vval, scope

        logger.debug("No matching value record found")
        return None

    def get_variable_definition(
        self, name: str, revision: int = -1
    ) -> tuple[VariableDefinitionRecord, Scope] | None:
        if revision < 0:
            return self._get_most_specific(name, "variable_definition")

        return next(
            (
                (vdef, scope)
                for scope in self.precedence_chain
                if (vdef := scope.get_variable_definition(name)) is not None
                and vdef.revision == revision
            ),
            None,
        )

    def set_variable_value(
        self, name: str, rec: VariableValueRecord, scope_level: ScopeLevel
    ) -> None:
        if scope_level.value >= 0:
            scope_ = self._get_most_specific_scope(
                lambda scope: scope.level is scope_level
            )
            if scope_ is None:
                raise RuntimeError(
                    "Attempting to access a scope which has not been entered"
                )
            scope_.set_variable_value(name, rec)
            return

        if scope_level is ScopeLevel.CURRENT_SCOPE:
            self.last_scope.set_variable_value(name, rec)
            return

        if scope_level is not ScopeLevel.OF_TEMPLATE:
            raise ValueError(f"Unsupported scope level: {scope_level}")

        assert isinstance(
            rec, ChangeableVariableValueRecord
        ), f"Internal error: constant variable value {rec!r} provided with scope level OF_TEMPLATE"

        tr = rec.template_record
        assert tr is not None
        _, limit = ensure_not_none(self.get_variable_definition(name, rec.revision))

        logger.debug(
            f"Searching for scope that contains {tr.used_variables!r}, stopping at {limit!r}"
        )
        # We're searching for the most general scope in which the variable's
        # expression can produce this value. This is the deepest scope in which
        # at least one of the expression's used variables is defined with the
        # given revision. We're limiting the search to the scope in which the
        # variable was defined, since above that scope, the variable would be
        # inaccessible.
        template_scope = self._get_outermost_scope_in_which_value_valid(tr)
        if template_scope is None:
            logger.debug(
                "Did not find matching scope, just adding to least specific possible"
            )
            scope_idx = self._scope_stack.index(limit)
        else:
            logger.debug(f"Found scope at level {template_scope.level.name}")
            scope_idx = max(
                self._scope_stack.index(template_scope), self._scope_stack.index(limit)
            )
        scope = self._scope_stack[scope_idx]
        logger.debug(
            f"Adding {rec!r} to scope of level {scope.level.name} (scope number {scope_idx})"
        )
        scope.set_variable_value(name, rec)

    def set_variable_definition(
        self, name: str, rec: VariableDefinitionRecord, scope_level: ScopeLevel
    ) -> None:
        if scope_level.value < 0:
            raise ValueError("Cannot store variable definition in relative scopes")

        scope_ = self._get_most_specific_scope(lambda scope: scope.level is scope_level)
        if scope_ is None:
            raise RuntimeError(
                "Attempting to access a scope which has not been entered"
            )
        scope_.set_variable_definition(name, rec)

    def get_expression(
        self, expr: str, used_values: list[VariableValueRecord]
    ) -> tuple[TemplateRecord, Scope] | None:
        logger.debug(
            f"Searching for previous evaluation of {expr!r} in reverse scope order"
        )
        for scope in self._scope_stack[::-1]:
            possible_tr = scope.get_expression(expr)
            if possible_tr is None:
                continue

            logger.debug(f"Found possible template record: {possible_tr!r}")

            if values_have_changed(possible_tr, used_values):
                logger.debug("Ignoring: Different value versions")
                continue

            logger.debug("Hit!")
            return possible_tr, scope

        logger.debug("Miss!")
        return None

    def set_expression(self, expr: str, rec: TemplateRecord) -> None:
        scope = self._get_outermost_scope_in_which_value_valid(rec)
        if scope is None:
            logger.debug(f"Found no suitable scope for template record {rec!r}")
            scope = self._scope_stack[0]
        logger.debug(
            f"Adding template record {rec!r} to scope of level {scope.level.name}"
        )
        scope.set_expression(expr, rec)

    def _get_most_specific_scope(self, pred: Callable[[Scope], bool]) -> Scope | None:
        for scope in self.precedence_chain:
            if pred(scope):
                return scope

        return None

    def _get_outermost_scope_in_which_value_valid(
        self, rec: TemplateRecord
    ) -> Scope | None:
        # We're looking for the outermost scope in which we can find every single
        # one of the variable values referenced by the template record, both
        # directly and indirectly. After this scope is popped, the value should
        # be invalidated.
        for scope in self._scope_stack:
            if self._scope_sees_all_values(scope, rec):
                return scope

        return None

    def _scope_sees_all_values(self, scope: Scope, rec: TemplateRecord) -> bool:
        scope_idx = self._scope_stack.index(scope)
        prec_chain = list(
            self._calculate_precedence_chain(self._scope_stack[: scope_idx + 1])
        )

        def get_val_from_scope(
            name: str, def_rev: int, val_rev: int
        ) -> VariableValueRecord | None:
            return next(
                (
                    sc.get_variable_value(name)
                    for sc in prec_chain
                    if sc.has_variable_value(name, def_rev, val_rev)
                ),
                None,
            )

        def is_visible(name: str, def_rev: int, val_rev: int) -> bool:
            return get_val_from_scope(name, def_rev, val_rev) is not None

        sees_all_direct_dependences = all(is_visible(*uv) for uv in rec.used_variables)
        if not sees_all_direct_dependences:
            return False

        # Check transitive dependences
        trans_tvals: list[TemplateRecord] = []
        for uv in rec.used_variables:
            vval = get_val_from_scope(*uv)
            assert (
                vval is not None
            )  # Impossible, we just checked that they're all visible
            if isinstance(vval, ChangeableVariableValueRecord):
                trans_tvals.append(vval.template_record)

        return (not trans_tvals) or all(
            self._scope_sees_all_values(scope, trans_tval) for trans_tval in trans_tvals
        )

    def get_variable_mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for scope in self._scope_stack:
            mapping |= scope.get_var_mapping()
        return mapping

    def get_currently_visible_definitions(self) -> set[tuple[str, int]]:
        visibles: dict[str, int] = {}
        for scope in reversed(list(self.precedence_chain)):
            visibles.update(scope.get_all_defined_variables())
        return set(visibles.items())

    def enter_scope(self, level: ScopeLevel) -> None:
        self._scope_stack.append(Scope(level))
        logger.debug(f"Entered {self._scope_stack[-1]}")

    def enter_cached_scope(self, level: ScopeLevel) -> None:
        self._scope_stack.append(Scope(level, is_cached=True))
        logger.debug(f"Entered {self._scope_stack[-1]}")

    def exit_scope(self) -> None:
        logger.debug(f"Leaving {self._scope_stack[-1]}")
        self._scope_stack.pop()


# TODO: Literal types
# TODO: Maybe simplify single-variable templates ("{{ var }}") to bypass
# intermediate values?
class VarContext:
    """Context for variable management."""

    def __init__(self, context: ExtractionContext) -> None:
        self._scopes = ScopeContext()
        self.context = context
        self._next_revnos: dict[str, int] = defaultdict(lambda: 0)
        self._next_valnos: dict[tuple[str, int], int] = {}
        self._valno_to_var: dict[tuple[str, int, int], tuple[rep.Variable, bool]] = {}

    @contextmanager
    def enter_scope(self, level: ScopeLevel) -> Generator[None, None, None]:
        self._scopes.enter_scope(level)
        yield
        self._scopes.exit_scope()

    @contextmanager
    def enter_cached_scope(self, level: ScopeLevel) -> Generator[None, None, None]:
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
            cached_val_record = self._scopes.last_scope.cached_results.get(
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
            self._scopes.last_scope.cached_results[var_name] = vr

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
                (val_record.name, val_record.revision, val_record.val_revision)
            ][0]

        for used_value in used_values:
            var_node = get_var_node_for_val_record(used_value)
            self.context.graph.add_edge(var_node, en, rep.USE)

        used_value_ids = [
            (vval.name, vval.revision, vval.val_revision) for vval in used_values
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
        self, name: str, level: ScopeLevel, *, expr: Any = SENTINEL
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
            val_record = ConstantVariableValueRecord(def_record, 0)
            self._scopes.set_variable_value(name, val_record, level)
        # If the variable isn't a constant value, we'll only create value records whenever it's evaluated

        return var_node

    def has_variable_at_scope(self, name: str, level: ScopeLevel) -> bool:
        return any(
            scope.level is level and scope.get_variable_definition(name) is not None
            for scope in self._scopes.precedence_chain
        )

    def _create_new_variable_node(
        self, vval: VariableValueRecord, scope: Scope
    ) -> rep.Variable:
        assert (
            vval.val_revision >= 1
        ), f"Internal Error: Unacceptable value version provided"
        var_node_idx = (vval.name, vval.revision, vval.val_revision)
        old_var_node, _ = self._valno_to_var[(vval.name, vval.revision, 0)]

        new_var_node = rep.Variable(
            name=vval.name,
            version=vval.revision,
            value_version=vval.val_revision,
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
            self.register_variable(name, ScopeLevel.CLI_VALUES)
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
        self._scopes.set_variable_value(name, value_record, ScopeLevel.OF_TEMPLATE)

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
