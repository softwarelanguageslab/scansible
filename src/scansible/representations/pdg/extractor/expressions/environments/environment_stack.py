from __future__ import annotations

from typing import Literal as LiteralT
from typing import overload

import operator
from collections.abc import Callable, Sequence
from itertools import chain

from loguru import logger

from scansible.utils.type_validators import ensure_not_none

from ..records import (
    ChangeableVariableValueRecord,
    ConstantVariableValueRecord,
    TemplateRecord,
    VariableDefinitionRecord,
    VariableValueRecord,
)
from .environment import Environment
from .types import GLOBAL_ENV_TYPES, LOCAL_ENV_TYPES, EnvironmentType, LocalEnvType


def _values_have_changed(
    tr: TemplateRecord, used_values: list[VariableValueRecord]
) -> bool:
    logger.debug(f"Checking whether dependences of {tr!r} match desired state")
    prev_used = sorted(tr.used_variables, key=lambda uv: uv[0])
    curr_used = sorted(
        [(uv.name, uv.revision, uv.value_revision) for uv in used_values],
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


class EnvironmentStack:
    """Collection of variable environments."""

    def __init__(self) -> None:
        global_env_order = sorted(GLOBAL_ENV_TYPES, key=operator.attrgetter("value"))
        self._global_environments = tuple(
            Environment(level) for level in global_env_order
        )
        self._local_environment_stack: list[Environment] = []

    @property
    def environment_stack(self) -> Sequence[Environment]:
        return tuple(chain(self._global_environments, self._local_environment_stack))

    @property
    def precedence_chain(self) -> Sequence[Environment]:
        return self._calculate_precedence_chain(self.environment_stack)

    def _calculate_precedence_chain(
        self, environments: Sequence[Environment]
    ) -> Sequence[Environment]:
        return sorted(environments, key=lambda scope: scope.level.value)[::-1]

    @property
    def current_environment(self) -> Environment:
        return self.environment_stack[-1]

    @overload
    def _get_most_specific(
        self, key: str, type: LiteralT["variable_value"]
    ) -> tuple[VariableValueRecord, Environment] | None:
        """See non-overloaded variant."""
        ...

    @overload
    def _get_most_specific(
        self, key: str, type: LiteralT["variable_definition"]
    ) -> tuple[VariableDefinitionRecord, Environment] | None:
        """See non-overloaded variant."""
        ...

    @overload
    def _get_most_specific(
        self, key: str, type: LiteralT["expression"]
    ) -> tuple[TemplateRecord, Environment] | None:
        ...

    def _get_most_specific(
        self,
        key: str,
        type: LiteralT["variable_value", "variable_definition", "expression"],
    ) -> (
        tuple[
            VariableValueRecord | VariableDefinitionRecord | TemplateRecord, Environment
        ]
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
    ) -> tuple[VariableValueRecord, Environment] | None:
        for scope in self.environment_stack[::-1]:
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
    ) -> tuple[VariableDefinitionRecord, Environment] | None:
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

    def set_constant_variable_value(
        self, name: str, rec: ConstantVariableValueRecord, scope_level: EnvironmentType
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

    def set_dynamic_variable_value(
        self, name: str, rec: ChangeableVariableValueRecord
    ) -> None:
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
            scope_idx = self.environment_stack.index(limit)
        else:
            logger.debug(f"Found scope at level {template_scope.level.name}")
            scope_idx = max(
                self.environment_stack.index(template_scope),
                self.environment_stack.index(limit),
            )
        scope = self.environment_stack[scope_idx]
        logger.debug(
            f"Adding {rec!r} to scope of level {scope.level.name} (scope number {scope_idx})"
        )
        scope.set_variable_value(name, rec)

    def set_variable_definition(
        self, name: str, rec: VariableDefinitionRecord, scope_level: EnvironmentType
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
    ) -> tuple[TemplateRecord, Environment] | None:
        logger.debug(
            f"Searching for previous evaluation of {expr!r} in reverse scope order"
        )
        for scope in self.environment_stack[::-1]:
            possible_tr = scope.get_expression(expr)
            if possible_tr is None:
                continue

            logger.debug(f"Found possible template record: {possible_tr!r}")

            if _values_have_changed(possible_tr, used_values):
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
            scope = self.environment_stack[0]
        logger.debug(
            f"Adding template record {rec!r} to scope of level {scope.level.name}"
        )
        scope.set_expression(expr, rec)

    def _get_most_specific_scope(
        self, pred: Callable[[Environment], bool]
    ) -> Environment | None:
        for scope in self.precedence_chain:
            if pred(scope):
                return scope

        return None

    def _get_outermost_scope_in_which_value_valid(
        self, rec: TemplateRecord
    ) -> Environment | None:
        # We're looking for the outermost scope in which we can find every single
        # one of the variable values referenced by the template record, both
        # directly and indirectly. After this scope is popped, the value should
        # be invalidated.
        for scope in self.environment_stack:
            if self._scope_sees_all_values(scope, rec):
                return scope

        return None

    def _scope_sees_all_values(self, scope: Environment, rec: TemplateRecord) -> bool:
        scope_idx = self.environment_stack.index(scope)
        prec_chain = list(
            self._calculate_precedence_chain(self.environment_stack[: scope_idx + 1])
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
        for scope in self.environment_stack:
            mapping |= scope.get_var_mapping()
        return mapping

    def get_currently_visible_definitions(self) -> set[tuple[str, int]]:
        visibles: dict[str, int] = {}
        for scope in reversed(list(self.precedence_chain)):
            visibles.update(scope.get_all_defined_variables())
        return set(visibles.items())

    def enter_scope(self, env_type: LocalEnvType) -> None:
        if env_type not in LOCAL_ENV_TYPES:
            raise ValueError("Attempted to enter a global environment")
        self._local_environment_stack.append(Environment(env_type))
        logger.debug(f"Entered {self.environment_stack[-1]}")

    def enter_cached_scope(self, env_type: LocalEnvType) -> None:
        if env_type not in LOCAL_ENV_TYPES:
            raise ValueError("Attempted to enter a global environment")
        self._local_environment_stack.append(Environment(env_type, is_cached=True))
        logger.debug(f"Entered {self.environment_stack[-1]}")

    def exit_scope(self) -> None:
        logger.debug(f"Leaving {self.environment_stack[-1]}")
        self._local_environment_stack.pop()
