from __future__ import annotations

from typing import TypeVar

import operator
from collections.abc import Callable, Iterable, Sequence
from functools import partial, reduce
from itertools import chain

from loguru import logger

from scansible.utils import first, first_where
from scansible.utils.type_validators import ensure_not_none

from ..records import (
    ChangeableVariableValueRecord,
    ConstantVariableValueRecord,
    TemplateEvaluationResult,
    TemplateRecord,
    VariableDefinitionRecord,
    VariableValueRecord,
)
from .environment import Environment
from .types import GLOBAL_ENV_TYPES, LOCAL_ENV_TYPES, EnvironmentType, LocalEnvType

_ElType = TypeVar("_ElType")


def _values_have_changed(
    tr: TemplateEvaluationResult, used_values: list[VariableValueRecord]
) -> bool:
    logger.debug(f"Checking whether dependences of {tr!r} match desired state")
    prev_used = sorted(tr.used_variables, key=operator.attrgetter("name"))
    curr_used = sorted(used_values, key=operator.attrgetter("name"))

    if len(prev_used) != len(curr_used):
        logger.debug(
            "Previous and current use different number of variables. DECISION: CHANGED"
        )
        return True
    # Pairwise check. We could arguably just do prev_used == curr_used but we want informative debug logs
    for prev, curr in zip(prev_used, curr_used):
        if prev != curr:
            logger.debug(
                f"Previous uses {prev.name}@{prev.revision}.{prev.value_revision}, "
                + f"current uses {curr.name}@{curr.revision}.{curr.value_revision}. "
                + "DECISION: CHANGED"
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
        return sorted(environments, key=lambda scope: scope.env_type.value)[::-1]

    @property
    def top_environment(self) -> Environment:
        return self.environment_stack[-1]

    def _get_highest_precedence_element(
        self,
        getter: Callable[[Environment], _ElType | None],
        predicate: Callable[[_ElType], bool],
    ) -> tuple[_ElType, Environment] | None:
        return first(
            (el, env)
            for env in self.precedence_chain
            if (el := getter(env)) is not None and predicate(el)
        )

    def _get_highest_precedence_variable_value(
        self,
        key: str,
        predicate: Callable[[VariableValueRecord], bool] = lambda _: True,
    ) -> tuple[VariableValueRecord, Environment] | None:
        return self._get_highest_precedence_element(
            operator.methodcaller("get_variable_value", key), predicate
        )

    def _get_highest_precedence_variable_definition(
        self,
        key: str,
        predicate: Callable[[VariableDefinitionRecord], bool] = lambda _: True,
    ) -> tuple[VariableDefinitionRecord, Environment] | None:
        return self._get_highest_precedence_element(
            operator.methodcaller("get_variable_definition", key), predicate
        )

    def _get_highest_precedence_expression(
        self,
        key: str,
        predicate: Callable[[TemplateEvaluationResult], bool] = lambda _: True,
    ) -> tuple[TemplateEvaluationResult, Environment] | None:
        return self._get_highest_precedence_element(
            operator.methodcaller("get_expression", key), predicate
        )

    def _get_topmost_environment(self, env_type: EnvironmentType) -> Environment:
        env = first_where(self.environment_stack, lambda env: env.env_type == env_type)
        if env is None:
            raise RuntimeError(
                "Attempting to access an environment which has not been entered"
            )
        return env

    def get_variable_definition(self, name: str) -> VariableDefinitionRecord | None:
        logger.debug(f"Looking up variable definition for {name!r}")
        result = self._get_highest_precedence_variable_definition(name)
        if result is None:
            logger.debug("Miss!")
            return None

        logger.debug(f"Hit! Found {result[0]!r} in {result[1]!r}")
        return result[0]

    def set_variable_definition(self, name: str, rec: VariableDefinitionRecord) -> None:
        self._get_topmost_environment(rec.env_type).set_variable_definition(name, rec)

    def _iter_variable_values(
        self, name: str
    ) -> Iterable[tuple[VariableValueRecord, Environment]]:
        # TODO: Why do we use the nesting order here instead of the precedence order?
        for env in reversed(self.environment_stack):
            vval = env.get_variable_value(name)
            if vval is not None:
                logger.debug(f"Found possible value for {name!r}: {vval!r}")
                yield vval, env

    def _iter_variable_values_for_definition(
        self, name: str, def_revision: int
    ) -> Iterable[tuple[VariableValueRecord, Environment]]:
        for vval, env in self._iter_variable_values(name):
            if vval.revision != def_revision:
                logger.debug("Ignoring: Wrong definition version")
                continue

            yield vval, env

    def has_variable_value(self, name: str) -> bool:
        return first(self._iter_variable_values(name)) is not None

    def get_variable_value_for_cached_expression(
        self, name: str, def_revision: int, template_record: TemplateRecord
    ) -> ChangeableVariableValueRecord | None:
        logger.debug(
            f"Looking up variable value for {name!r}@{def_revision}, evaluated as {template_record!r}"
        )
        for vval, env in self._iter_variable_values_for_definition(name, def_revision):
            if not isinstance(vval, ChangeableVariableValueRecord):
                logger.debug("Ignoring: Expecting changeable value")
                continue

            if vval.template_record != template_record:
                logger.debug(
                    f"Ignoring: Wrong template record: {vval.template_record!r} vs {template_record!r}"
                )
                continue

            logger.debug(f"Hit! Found {vval!r} in {env!r}")
            return vval

        logger.debug("No matching value record found")
        return None

    def get_variable_value_for_constant_definition(
        self, name: str, def_revision: int
    ) -> ConstantVariableValueRecord | None:
        logger.debug(f"Looking up constant value for {name!r}@{def_revision}")
        for vval, env in self._iter_variable_values_for_definition(name, def_revision):
            if not isinstance(vval, ConstantVariableValueRecord):
                logger.debug("Ignoring: Expecting constant value")
                continue

            logger.debug(f"Hit! Found {vval!r} in {env!r}")
            return vval

        logger.debug("No matching value record found")
        return None

    def set_constant_variable_value(
        self, name: str, rec: ConstantVariableValueRecord
    ) -> None:
        self._get_topmost_environment(
            rec.variable_definition.env_type
        ).set_variable_value(name, rec)

    def set_changeable_variable_value(
        self, name: str, rec: ChangeableVariableValueRecord
    ) -> None:
        # The environment in which the expression is evaluated isn't necessarily
        # the same environment as where the variable is defined. The expression
        # may also depend on variables that are defined in deeper environments.
        # We'll thus find the outermost environment in which this variable's
        # expression would evaluate to this value, and store the value in that
        # environment.
        target_env = self._find_env_for_evaluated_variable(
            name, rec.revision, rec.template_record
        )
        logger.debug(f"Adding {rec!r} to env of type {target_env.env_type.name}")
        target_env.set_variable_value(name, rec)

    def _find_env_for_evaluated_variable(
        self, name: str, def_revision: int, template_record: TemplateRecord
    ) -> Environment:
        _, outermost_env = ensure_not_none(
            self._get_highest_precedence_variable_definition(
                name, lambda vdef: vdef.revision == def_revision
            )
        )

        logger.debug(
            f"Searching for environment that contains {template_record.used_variables!r}, "
            + f"stopping at {outermost_env!r}"
        )

        # We're searching for the most general environment in which the template
        # record's evaluation is valid, i.e., the deepest environment in which
        # all of the expression's referenced variables would evaluate to the
        # data used in the actual evaluation.
        # We're limiting the search to the env in which the variable was defined,
        # since outside of that env, the variable would be inaccessible.
        template_env = self._get_outermost_env_for_template(template_record)
        if template_env is None:
            # TODO: Can this even happen? If so, how and why?
            logger.debug(
                "Did not find matching environment, just adding to outermost possible"
            )
            env_idx = self.environment_stack.index(outermost_env)
        else:
            logger.debug(f"Found environment of type {template_env.env_type.name}")
            env_idx = max(
                self.environment_stack.index(template_env),
                self.environment_stack.index(outermost_env),
            )

        return self.environment_stack[env_idx]

    def _get_outermost_env_for_template(
        self, rec: TemplateRecord
    ) -> Environment | None:
        # We're looking for the outermost scope in which we can find every single
        # one of the variable values referenced by the template record, both
        # directly and indirectly. After this scope is popped, the evaluation
        # should be invalidated.
        return first_where(
            self.environment_stack,
            partial(self._all_used_values_are_visible_in_env, rec=rec),
        )

    def _all_used_values_are_visible_in_env(
        self, env: Environment, rec: TemplateRecord
    ) -> bool:
        scope_idx = self.environment_stack.index(env)
        prec_chain = list(
            self._calculate_precedence_chain(self.environment_stack[: scope_idx + 1])
        )

        def is_visible(vval: VariableValueRecord) -> bool:
            highest_prec_vval = first(
                candidate_vval
                for env in prec_chain
                if (candidate_vval := env.get_variable_value(vval.name)) is not None
            )
            return highest_prec_vval is not None and highest_prec_vval == vval

        sees_all_direct_dependences = all(is_visible(uv) for uv in rec.used_variables)
        if not sees_all_direct_dependences:
            return False

        # Check transitive dependences
        transitive_dependences: list[TemplateRecord] = []
        for used_var in rec.used_variables:
            # Cannot be none, we just checked that they're all visible
            if isinstance(used_var, ChangeableVariableValueRecord):
                transitive_dependences.append(used_var.template_record)

        return (not transitive_dependences) or all(
            self._all_used_values_are_visible_in_env(env, trans_dep)
            for trans_dep in transitive_dependences
        )

    def get_expression_evaluation_result(
        self, expr: str, used_values: list[VariableValueRecord]
    ) -> TemplateEvaluationResult | None:
        logger.debug(f"Searching for previous evaluation of {expr!r}")
        # TODO: Why are we using the reverse nesting order here,
        # instead of precedence order?
        for env in reversed(self.environment_stack):
            possible_tr = env.get_expression_evaluation_result(expr)
            if possible_tr is None:
                continue

            logger.debug(f"Found possible template record: {possible_tr!r}")

            if _values_have_changed(possible_tr, used_values):
                logger.debug("Ignoring: Different value versions")
                continue

            logger.debug(f"Hit! Found {possible_tr!r} in {env!r}")
            return possible_tr

        logger.debug("Miss!")
        return None

    def set_expression_evaluation_result(
        self, expr: str, rec: TemplateEvaluationResult
    ) -> None:
        env = self._get_outermost_env_for_template(rec)
        if env is None:
            # TODO: Can this even happen?
            logger.debug(f"Found no suitable environment for template record {rec!r}")
            env = self.environment_stack[0]
        logger.debug(
            f"Adding template record {rec!r} to environment of type {env.env_type.name}"
        )
        env.set_expression_evaluation_result(expr, rec)

    def _get_all_visible_definitions(self) -> dict[str, VariableDefinitionRecord]:
        return reduce(
            operator.or_,
            (
                env.get_all_variable_definitions()
                for env in reversed(self.precedence_chain)
            ),
        )

    def get_variable_initialisers(self) -> dict[str, str]:
        all_vars = self._get_all_visible_definitions()

        # Need to do the filtering for vars without initialisers at the end
        # instead of while iterating, because a var without an initialiser may
        # override a var with an initialiser.
        return {
            vdef.name: vdef.initialiser
            for vdef in all_vars.values()
            if isinstance(vdef.initialiser, str)
        }

    def get_currently_visible_definitions(self) -> set[tuple[str, int]]:
        all_vars = self._get_all_visible_definitions()
        return set((vdef.name, vdef.revision) for vdef in all_vars.values())

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
