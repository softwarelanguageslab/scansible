from __future__ import annotations

from typing import cast, overload, Any, Generator, Literal as LiteralT, NamedTuple, Optional, Union, TYPE_CHECKING

from collections import defaultdict
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from enum import Enum

from loguru import logger

from ansible_graph_extractor.models.edges import DEF, USE
from ansible_graph_extractor.models.graph import Graph
from ansible_graph_extractor.models.nodes import DataNode, Expression, IntermediateValue, Literal, Variable

if TYPE_CHECKING:
    from .context import ExtractionContext

from ansible_graph_extractor.extractor.templates import TemplateExpressionAST, LookupTargetLiteral

class TemplateRecord(NamedTuple):
    """State of a template expression."""
    data_node: DataNode
    expr_node: Expression
    used_variables: list[tuple[str, int, int]]
    may_be_dynamic: bool
    is_literal: bool

    def __repr__(self) -> str:
        return f'TemplateRecord(expr={self.expr_node.expr!r}, data_node={self.data_node.node_id}, expr_node={self.expr_node.node_id})'


class VariableDefinitionRecord(NamedTuple):
    """Binding of a variable at any given time."""
    name: str
    revision: int
    template_expr: Union[str, Sentinel]

    def __repr__(self) -> str:
        return f'VariableDefinitionRecord(name={self.name!r}, revision={self.revision}, expr={self.template_expr!r})'

class VariableValueRecord(NamedTuple):
    """Binding of a variable at any given time."""
    var_def: VariableDefinitionRecord
    var_node: Variable
    val_revision: int
    template_record: Optional[TemplateRecord] = None

    @property
    def name(self) -> str:
        return self.var_def.name

    @property
    def revision(self) -> int:
        return self.var_def.revision

    def __repr__(self) -> str:
        return f'VariableValueRecord(var_def={self.var_def!r}, var_node={self.var_node.node_id}, val_revision={self.val_revision})'

class Sentinel:
    def __repr__(self) -> str:
        return f'SENTINEL'

SENTINEL = Sentinel()


STATIC_LOOKUP_PLUGINS = {
    'config',
    'dict',
    'indexed_items',
    'items',
    'list',
    'nested',
    'sequence',
    'subelements',
    'together',
    'cartesian',

    # TODO: This isn't idempotent, but we need a better way to filter these out
    # as they lead to many false positives
    'env',
}

STATIC_FILTERS = {
    # Jinja2 built-in
    'abs',
    'attr',
    'batch',
    'capitalize',
    'center',
    'default', 'd',
    'dictsort',
    'escape', 'e',
    'filesizeformat',
    'first',
    'float',
    'forceescape',
    'format',
    'groupby',
    'indent',
    'int',
    'join',
    'last',
    'length', 'count',
    'list',
    'lower',
    'map',
    'max',
    'min',
    'pprint',
    'reject',
    'rejectattr',
    'replace',
    'reverse',
    'round',
    'safe',
    'select',
    'selectattr',
    'slice',
    'sort',
    'string',
    'striptags',
    'sum',
    'title',
    'tojson',
    'trim',
    'truncate',
    'unique',
    'upper',
    'urlencode',
    'urlize',
    'wordcount',
    'wordwrap',
    'xmlattr',
    # Ansible built-ins
    'b64decode',
    'b64encode',
    'to_uuid',
    'to_json',
    'to_nice_json',
    'from_json',
    'to_yaml',
    'to_nice_yaml',
    'from_yaml',
    'from_yaml_all',
    'basename',
    'dirname',
    'expanduser',
    'path_join',
    'relpath',
    'splitext',
    'win_basename',
    'win_dirname',
    'win_splitdrive',
    'bool',
    'to_datetime',
    'strftime',
    'quote',
    'md5',
    'sha1',
    'checksum',
    'password_hash',
    'hash',
    'regex_replace',
    'regex_escape',
    'regex_search',
    'regex_findall',
    'ternary',
    'mandatory',
    'comment',
    'type_debug',
    'combine',
    'extract',
    'flatten',
    'dict2items',
    'items2dict',
    'subelements',
    'split',
    'urldecode',
    'urlencode',
    'urlsplit',
    'min',
    'max',
    'log',
    'pow',
    'root',
    'unique',
    'intersect',
    'difference',
    'symmetric_difference',
    'union',
    'product',
    'permutations',
    'combinations',
    'human_readable',
    'human_to_bytes',
    'rekey_on_member',
    'zip',
    'zip_longest',
    'json_query',
    'ipaddr',
    'version_compare',
}

STATIC_TESTS = {
    # Jinja2 built-in
    'boolean',
    'callable',
    'defined',
    'divisibleby',
    'eq', 'equalto', '=='
    'escaped',
    'even',
    'false',
    'filter',
    'float',
    'ge', '>=',
    'gt', 'greaterthan', '>'
    'in',
    'integer',
    'iterable',
    'le', '<=',
    'lower',
    'lt', '<', 'lessthan',
    'mapping',
    'ne', '!=',
    'none',
    'number',
    'odd',
    'sameas',
    'sequence',
    'string',
    'true',
    'undefined',
    'upper',
    # Ansible built-in
    'match',
    'search',
    'regex',
    'version_compare',
    'version',
    'any',
    'all',
    'truthy',
    'falsy',
    'vault_encrypted',
    'is_abs',
    'abs',
    'issubset',
    'subset',
    'issuperset',
    'superset',
    'contains',
    'isnan',
    'nan'
}


def expr_may_be_dynamic(ast: TemplateExpressionAST) -> bool:
    return (ast.uses_now
            or any(filter_op not in STATIC_FILTERS for filter_op in ast.used_filters)
            or any(test_op not in STATIC_TESTS for test_op in ast.used_tests)
            or any(
                (not isinstance(lookup_op, LookupTargetLiteral))
                 or (lookup_op.name not in STATIC_LOOKUP_PLUGINS)
                for lookup_op in ast.used_lookups))


class Scope:
    def __init__(self, level: ScopeLevel, is_cached: bool = False) -> None:
        self.level = level
        self.is_cached = is_cached
        # Values of expressions valid in this scope
        self._expr_store: dict[str, TemplateRecord] = {}
        # Variables defined in this scope
        self._var_def_store: dict[str, VariableDefinitionRecord] = {}
        # Values of variables in this scope. Variable itself can come from an
        # outer scope, but its value may depend on variables defined within
        # this scope
        self._var_val_store: dict[str, VariableValueRecord] = {}

    def __repr__(self) -> str:
        return f'Scope(level={self.level.name}, is_cached={self.is_cached})'

    def get_variable_definition(self, name: str) -> Optional[VariableDefinitionRecord]:
        return self._var_def_store.get(name)

    def set_variable_definition(self, name: str, rec: VariableDefinitionRecord) -> None:
        self._var_def_store[name] = rec

    def has_variable_definition(self, name: str, revision: int) -> bool:
        return (name in self._var_def_store
                and self._var_def_store[name].revision == revision)

    def get_variable_value(self, name: str) -> Optional[VariableValueRecord]:
        return self._var_val_store.get(name)

    def set_variable_value(self, name: str, rec: VariableValueRecord) -> None:
        self._var_val_store[name] = rec

    def has_variable_value(self, name: str, def_rev: int, val_rev: int) -> bool:
        return (name in self._var_val_store
                and self._var_val_store[name].revision == def_rev
                and self._var_val_store[name].val_revision == val_rev)

    def get_var_mapping(self) -> dict[str, str]:
        return {vr.name: vr.template_expr
                for vr in self._var_def_store.values()
                if not isinstance(vr.template_expr, Sentinel)}

    def get_expression(self, expr: str) -> Optional[TemplateRecord]:
        return self._expr_store.get(expr)

    def set_expression(self, expr: str, rec: TemplateRecord) -> None:
        self._expr_store[expr] = rec

    def has_expression(self, expr: str) -> bool:
        return expr in self._expr_store

    def __str__(self) -> str:
        out = 'Scope@' + self.level.name
        locals_str = ', '.join(f'{v.name}@{v.revision}' for v in self._var_def_store.values()) or 'none'
        values_str = ', '.join(f'{v.name}@{v.revision}.{v.val_revision}' for v in self._var_val_store.values()) or 'none'
        exprs_str = ', '.join(e.expr_node.expr + (' (dynamic)' if e.may_be_dynamic else '') for e in self._expr_store.values() if not e.is_literal) or 'none'
        return f'{out} (locals: {locals_str}, values: {values_str}, expressions: {exprs_str})'


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

class ScopeContext:
    """Collection of variable scopes."""

    def __init__(self) -> None:
        self._scope_stack: list[Scope] = []
        for level in sorted(
                set(ScopeLevel) - STACKABLE_SCOPES,
                key=lambda level: level.value):
            if level.value < 0:
                continue
            self._scope_stack.append(Scope(level))

    @property
    def _precedence_chain(self) -> Iterable[Scope]:
        return sorted(
                self._scope_stack,
                key=lambda scope: scope.level.value)[::-1]

    @property
    def last_scope(self) -> Scope:
        return self._scope_stack[-1]

    @overload
    def _get_most_specific(self, key: str, type: LiteralT['variable_value']) -> Optional[VariableValueRecord]:
        """See non-overloaded variant."""
        ...

    @overload
    def _get_most_specific(self, key: str, type: LiteralT['variable_definition']) -> Optional[VariableDefinitionRecord]:
        """See non-overloaded variant."""
        ...

    @overload
    def _get_most_specific(self, key: str, type: LiteralT['expression']) -> Optional[TemplateRecord]:
        ...

    def _get_most_specific(
            self, key: str, type: LiteralT['variable_value', 'variable_definition', 'expression']
    ) -> Union[VariableValueRecord, VariableDefinitionRecord, TemplateRecord, None]:
        return next((
                rec for scope in self._precedence_chain
                if (rec := getattr(scope, f'get_{type}')(key)) is not None),
            None)

    def get_variable_value(self, name: str, revision: int = -1) -> Optional[VariableValueRecord]:
        if revision < 0:
            return self._get_most_specific(name, 'variable_value')

        return next(
                (vval for scope in self._precedence_chain
                    if (vval := scope.get_variable_value(name)) is not None
                    and vval.revision == revision),
                None)

    def get_variable_definition(self, name: str) -> Optional[VariableDefinitionRecord]:
        return self._get_most_specific(name, 'variable_definition')

    def get_variable_definition_scope(self, name: str) -> Scope:
        return next(
                scope for scope in self._precedence_chain
                if scope.get_variable_definition(name) is not None)

    def get_variable_value_scope(self, name: str) -> Scope:
        return next(
                scope for scope in self._precedence_chain
                if scope.get_variable_value(name) is not None)

    def set_variable_value(
            self, name: str, rec: VariableValueRecord, scope_level: ScopeLevel
    ) -> None:
        if scope_level.value >= 0:
            scope_ = self._get_most_specific_scope(
                lambda scope: scope.level is scope_level)
            if scope_ is None:
                raise RuntimeError(
                        'Attempting to access a scope which has '
                        'not been entered')
            scope_.set_variable_value(name, rec)
            return

        if scope_level is ScopeLevel.CURRENT_SCOPE:
            self.last_scope.set_variable_value(name, rec)
            return

        if scope_level is not ScopeLevel.OF_TEMPLATE:
            raise ValueError(f'Unsupported scope level: {scope_level}')

        tr = rec.template_record
        assert tr is not None
        limit = self.get_variable_definition_scope(name)
        logger.debug(f'Searching for scope that contains {tr.used_variables!r}, stopping at {limit!r}')
        # We're searching for the most general scope in which the variable's
        # expression can produce this value. This is the deepest scope in which
        # at least one of the expression's used variables is defined with the
        # given revision. We're limiting the search to the scope in which the
        # variable was defined, since above that scope, the variable would be
        # inaccessible.
        template_scope = self._get_most_specific_scope(
                lambda scope, tr=tr: any(  # type: ignore[misc]
                    scope.has_variable_value(name, def_rev, val_rev)
                    for name, def_rev, val_rev in tr.used_variables))
        if template_scope is None:
            logger.debug('Did not find matching scope, just adding to least specific possible')
            scope_idx = self._scope_stack.index(limit)
        else:
            scope_idx = max(
                    self._scope_stack.index(template_scope),
                    self._scope_stack.index(limit))
        scope = self._scope_stack[scope_idx]
        logger.debug(f'Adding {rec!r} to scope of level {scope.level.name} (scope number {scope_idx})')
        scope.set_variable_value(name, rec)

    def set_variable_definition(
            self, name: str, rec: VariableDefinitionRecord, scope_level: ScopeLevel
    ) -> None:
        if scope_level.value < 0:
            raise ValueError('Cannot store variable definition in relative scopes')

        scope_ = self._get_most_specific_scope(
                lambda scope: scope.level is scope_level)
        if scope_ is None:
            raise RuntimeError(
                    'Attempting to access a scope which has '
                    'not been entered')
        scope_.set_variable_definition(name, rec)

    def get_expression(self, expr: str) -> Optional[TemplateRecord]:
        return self._get_most_specific(expr, 'expression')

    def set_expression(self, expr: str, rec: TemplateRecord) -> None:
        scope = self._get_most_specific_scope(
                lambda scope: any(
                    scope.has_variable_value(name, def_rev, val_rev)
                    for name, def_rev, val_rev in rec.used_variables))
        if scope is None:
            scope = self._scope_stack[0]
        scope.set_expression(expr, rec)

    def _get_most_specific_scope(
            self, pred: Callable[[Scope], bool]
    ) -> Scope | None:
        for scope in self._precedence_chain:
            if pred(scope):
                return scope

        return None

    def get_variable_mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for scope in self._scope_stack:
            mapping |= scope.get_var_mapping()
        return mapping

    def enter_scope(self, level: ScopeLevel) -> None:
        self._scope_stack.append(Scope(level))
        logger.debug(f'Entered {self._scope_stack[-1]}')

    def enter_cached_scope(self, level: ScopeLevel) -> None:
        self._scope_stack.append(Scope(level, is_cached=True))
        logger.debug(f'Entered {self._scope_stack[-1]}')

    def exit_scope(self) -> None:
        logger.debug(f'Leaving {self._scope_stack[-1]}')
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

    def evaluate_template(self, expr: str, g: Graph, is_conditional: bool) -> TemplateRecord:
        """Parse a template, add required nodes to the graph, and return the record."""
        logger.debug(f'Evaluating expression {expr!r}')
        prev_evaluated = self._get_template_record(expr)
        if prev_evaluated is not None:
            return self._maybe_reevaluate(prev_evaluated, g, is_conditional)

        logger.debug(f'First time evaluating {expr!r}')
        ret =  self._evaluate_template(expr, g, is_conditional)
        logger.debug(f'Finished first evaluation of {expr!r}')
        return ret

    def add_literal(self, value: Any, g: Graph) -> Literal:
        type_ = value.__class__.__name__
        if isinstance(value, (dict, list)):
            self.context.graph.errors.append('I am not able to handle composite literals yet')
            lit = Literal(node_id=self.context.next_id(), type=type_, value='')
        else:
            lit = Literal(node_id=self.context.next_id(), type=type_, value=value)

        g.add_node(lit)
        return lit

    def register_variable(self, name: str, level: ScopeLevel, graph: Graph, *, expr: Any = SENTINEL) -> Variable:
        """Declare a variable, initialized with the given expression.

        Expression may be empty if not available.

        Returns the newly created variable, may be added by to the graph by
        the client. If not added to the graph by the client, will be added
        when a template that uses this variable is evaluated.
        """
        logger.debug(f'Registering variable {name} of type {type(expr).__name__} at scope level {level.name}')
        var_rev = self._next_revnos[name]
        self._next_revnos[name] += 1
        self._next_valnos[(name, var_rev)] = 1

        logger.debug(f'Selected revision {var_rev} for {name}')
        var_node = Variable(node_id=self.context.next_id(), name=name, version=var_rev, value_version=0, scope_level=level.value)
        graph.add_node(var_node)

        if isinstance(expr, str) and (ast := TemplateExpressionAST.parse(expr, False, self._scopes.get_variable_mapping())) is not None and not ast.is_literal():
            template_expr: str | Sentinel = expr
        elif expr is SENTINEL:
            template_expr = SENTINEL
        else:
            template_expr = SENTINEL
            lit_node = self.add_literal(expr, graph)
            graph.add_edge(lit_node, var_node, DEF)

        def_record = VariableDefinitionRecord(name, var_rev, template_expr)
        val_record = VariableValueRecord(def_record, var_node, 0)

        self._scopes.set_variable_definition(name, def_record, level)
        self._scopes.set_variable_value(name, val_record, level)
        return var_node

    def has_variable_at_scope(self, name: str, level: ScopeLevel) -> bool:
        return next((
                True for scope in self._scopes._precedence_chain
                if scope.level is level and scope.get_variable_definition(name) is not None),
            False)

    def _get_template_record(self, expr: str | Sentinel) -> Optional[TemplateRecord]:
        if not isinstance(expr, Sentinel):
            return self._scopes.get_expression(expr)
        return None

    def _template_dependencies_have_changed(self, prev: TemplateRecord) -> bool:
        logger.debug(f'Checking whether dependencies of {prev!r} have changed')
        for var_name, def_rev, val_rev in prev.used_variables:
            curr_def = self._scopes.get_variable_definition(var_name)
            if curr_def is None:
                logger.debug(f'{var_name} ({def_rev}, {val_rev}) does not exist yet. DECISION: CHANGED')
                return True
            curr_val = self._scopes.get_variable_value(var_name, curr_def.revision)
            if curr_val is None:
                logger.debug(f'{var_name} ({def_rev}, {val_rev}) does not exist yet. DECISION: CHANGED')
                return True
            if curr_def.revision != def_rev:
                logger.debug(f'{var_name} definition has been rebound: Template was previously evaluated defined with {def_rev}, variable is now {curr_def.revision}. DECISION: CHANGED')
                return True
            if curr_val.val_revision != val_rev:
                logger.debug(f'{var_name} value has changed: Template was previously evaluated defined with {val_rev}, variable is now {curr_val.val_revision}. DECISION: CHANGED')
                return True
            if self._variable_has_changed(curr_val):
                logger.debug(f'Expression defining {var_name} has changed. DECISION: CHANGED')
                return True

        logger.debug('Variables have not changed. DECISION: UNCHANGED')
        return False

    def _variable_has_changed(self, var: VariableValueRecord) -> bool:
        logger.debug(f'Checking whether expression defining {var!r} has changed')
        tr = var.template_record
        if tr is None:
            logger.debug('Evaluation of expression not stored, assuming unchanged')
            return False
        new_tr = self._get_template_record(var.var_def.template_expr)
        if tr is not new_tr:
            logger.debug('Template record of value has changed in current scope, variable too')
            return True

        if (self._scopes.get_variable_value_scope(var.name) is self._scopes.last_scope
                and self._scopes.last_scope.is_cached):
            logger.debug('Variable is evaluated in the current scope, current scope is cached => variable has not changed')
            return False

        tmpl_changed = self._template_result_has_changed(tr)
        if tmpl_changed:
            logger.debug('Expression result changed, so variable too')
        else:
            logger.debug('Expression result unchanged, variable has not changed')
        return tmpl_changed

    def _template_result_has_changed(self, prev: TemplateRecord) -> bool:
        if prev.may_be_dynamic:
            logger.debug(f'{prev!r} is a dynamic expression, assuming changed')
            return True
        return self._template_dependencies_have_changed(prev)

    def _maybe_reevaluate(self, prev: TemplateRecord, g: Graph, is_conditional: bool) -> TemplateRecord:
        logger.debug(f'Checking whether {prev!r} needs to be re-evaluated')
        if not self._template_result_has_changed(prev):
            logger.debug(f'Result of {prev!r} has not changed, reusing previous result')
            return prev

        if not self._template_dependencies_have_changed(prev):
            iv_id = self.context.next_iv_id()
            logger.debug(f'Dependencies have not changed, but expression is not idempotent. Creating new IV ({iv_id}) to represent new result')
            iv = IntermediateValue(node_id=self.context.next_id(), identifier=iv_id)
            g.add_edge(prev.expr_node, iv, DEF)
            return TemplateRecord(iv, prev.expr_node, prev.used_variables, prev.may_be_dynamic, prev.is_literal)

        logger.debug('Template dependencies have changed, need to re-evaluate in full')
        return self._evaluate_template(prev.expr_node.expr, g, is_conditional)

    def _get_variable_value_record(self, name: str, g: Graph) -> VariableValueRecord:
        """Get a variable value record for a variable.

        If the variable is undefined, declares a new variable.
        If the variable is defined, will return a variable and evaluate its
        initializer, if necessary.
        """
        logger.debug(f'Resolving variable {name}')
        vdef = self._scopes.get_variable_definition(name)

        # Undefined variables: Assume lowest scope
        if vdef is None:
            logger.debug(f'Variable {name} has not yet been defined, registering new value at lowest precedence level')
            self.register_variable(name, ScopeLevel.CLI_VALUES, graph=g)
            vr = self._scopes.get_variable_value(name)
            assert vr is not None
            return vr

        expr = vdef.template_expr
        logger.debug(f'Found existing variable {vdef!r}')

        vr = self._scopes.get_variable_value(name, vdef.revision)
        assert vr is not None, 'Variable defined without value?!'
        logger.debug(f'Found existing variable value {vr!r}')

        # No template expression -> Cannot be evaluated, just return as is
        if isinstance(expr, Sentinel):
            logger.debug('Variable has no initializer, cannot evaluate. Assuming unchanged.')
            return vr

        tr = vr.template_record or self._get_template_record(expr)
        logger.debug(f'Using template record {tr!r} as initializer for {name!r}')
        if tr is vr.template_record:
            logger.debug(f'TR is reused from previous variable record')

        # Template hasn't been evaluated yet -> Evaluate it
        # Create a new node to represent newly-evaluated template
        if tr is None:
            logger.debug(f'Evaluating initializer for {vr!r}')
            tr = self._evaluate_template(expr, g, False)
            new_val_rev = self._next_valnos[(name, vr.revision)]
            self._next_valnos[(name, vr.revision)] += 1
            vn = Variable(node_id=self.context.next_id(), name=name, version=vr.revision, value_version=new_val_rev, scope_level=self._scopes.get_variable_definition_scope(name).level.value)
            g.add_edge(tr.data_node, vn, DEF)
            new_vr = vr._replace(template_record=tr, var_node=vn)
            if self._scopes.last_scope.is_cached and tr.may_be_dynamic:
                # Current scope is cached and template is dynamic. Create a
                # cached copy of the variable in this current scope for reuse.
                logger.debug(f'Storing {new_vr!r} in current cached scope')
                self._scopes.set_variable_value(name, new_vr, ScopeLevel.CURRENT_SCOPE)
            else:
                logger.debug(f'Storing {new_vr!r} in most general scope of template')
                self._scopes.set_variable_value(name, new_vr, ScopeLevel.OF_TEMPLATE)
            return new_vr

        # Try to re-evaluate if necessary, e.g. when the template is dynamic
        # or a nested expression has changed. Skip re-evaluating if the
        # variable originates from this scope and this scope is cached
        if (self._scopes.get_variable_value_scope(name) is self._scopes.last_scope
                and self._scopes.last_scope.is_cached):
            # Variable comes from this scope's cache, can reuse it
            logger.debug(f'{name} comes from a cached scope, reusing as-is')
            return vr

        new_tr = self._maybe_reevaluate(tr, g, False)
        if new_tr is vr.template_record:
            logger.debug(f'Initializer for {name} has not changed, reusing')
            # Unchanged, same variable
            g.add_edge(tr.data_node, vr.var_node, DEF)
            return vr

        # Can still be unchanged w.r.t. already evaluated expr, but the VR
        # may still be using another TR.

        # Variable changed -> Create new revision
        logger.debug(f'Initializer for {name} has changed, creating new value revision')
        new_val_rev = self._next_valnos[(name, vr.revision)]
        self._next_valnos[(name, vr.revision)] += 1
        vn = Variable(node_id=self.context.next_id(), name=name, version=vr.revision, value_version=new_val_rev, scope_level=self._scopes.get_variable_definition_scope(name).level.value)
        new_vr = vr._replace(val_revision=new_val_rev, template_record=new_tr, var_node=vn)

        if self._scopes.last_scope.is_cached and new_tr.may_be_dynamic:
            logger.debug(f'Storing {new_vr!r} in current scope, since it is dynamic and the scope is cached')
            self._scopes.set_variable_value(name, new_vr, ScopeLevel.CURRENT_SCOPE)
        else:
            logger.debug(f'Storing {new_vr!r} in scope of template or deeper')
            self._scopes.set_variable_value(name, new_vr, ScopeLevel.OF_TEMPLATE)

        logger.debug(f'Adding variable node {vn!r}')
        g.add_node(vn)
        logger.debug(f'Linking data node {new_tr.data_node!r} of TR {new_tr!r} to {vn!r}')
        g.add_edge(new_tr.data_node, vn, DEF)
        return new_vr

    def _evaluate_template(self, expr: str, g: Graph, is_conditional: bool) -> TemplateRecord:
        logger.debug(f'Evaluating template {expr!r}')
        en = Expression(node_id=self.context.next_id(), expr=expr)
        ast = TemplateExpressionAST.parse(expr, is_conditional, self._scopes.get_variable_mapping())

        if ast is None or ast.is_literal():
            logger.debug(f'{expr!r} is a literal or broken expression')
            ln = Literal(node_id=self.context.next_id(), value=expr, type='str')
            g.add_node(ln)
            return TemplateRecord(ln, en, [], False, True)

        iv = IntermediateValue(node_id=self.context.next_id(), identifier=self.context.next_iv_id())
        logger.debug(f'Using IV {iv.identifier}')
        g.add_node(en)
        g.add_node(iv)
        g.add_edge(en, iv, DEF)

        used_variables: list[tuple[str, int, int]] = []
        for var_name in ast.referenced_variables:
            logger.debug(f'Linking data for used variable {var_name}')
            try:
                vr = self._get_variable_value_record(var_name, g)
            except RecursionError:
                raise RecursionError(f'Recursive definition detected in {expr!r}') from None
            logger.debug(f'Determined that {expr!r} uses {vr!r}')
            g.add_edge(vr.var_node, en, USE)
            used_variables.append((vr.var_node.name, vr.revision, vr.val_revision))

        tr = TemplateRecord(iv, en, used_variables, expr_may_be_dynamic(ast), False)
        self._scopes.set_expression(expr, tr)
        return tr
