from __future__ import annotations

from typing import final

import operator
from collections.abc import Callable, Sequence
from functools import reduce
from itertools import chain

from loguru import logger

from scansible.representations import ast
from scansible.representations.pdg.representation import Variable
from scansible.utils import first, first_where

from ..records import VariableDefinitionRecord
from .environment import Environment
from .types import GLOBAL_ENV_TYPES, LOCAL_ENV_TYPES, EnvironmentType, LocalEnvType


@final
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

    def _get_highest_precedence_element[E](
        self,
        getter: Callable[[Environment], E | None],
        predicate: Callable[[E], bool],
    ) -> tuple[E, Environment] | None:
        return first(
            (el, env)
            for env in self.precedence_chain
            if (el := getter(env)) is not None and predicate(el)
        )

    def _get_highest_precedence_variable_definition(
        self,
        key: str,
        predicate: Callable[[VariableDefinitionRecord], bool] = lambda _: True,
    ) -> tuple[VariableDefinitionRecord, Environment] | None:
        return self._get_highest_precedence_element(
            operator.methodcaller("get_variable_definition", key), predicate
        )

    def _get_topmost_environment(self, env_type: EnvironmentType) -> Environment:
        env = first_where(
            self.environment_stack[::-1], lambda env: env.env_type == env_type
        )
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

    def _get_all_visible_definitions(self) -> dict[str, VariableDefinitionRecord]:
        return reduce(
            operator.or_,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            (
                env.get_all_variable_definitions()
                for env in reversed(self.precedence_chain)
            ),
        )

    def get_variable_initialisers(self) -> dict[str, ast.AnyExpression]:
        all_vars = self._get_all_visible_definitions()

        # Need to do the filtering for vars without initialisers at the end
        # instead of while iterating, because a var without an initialiser may
        # override a var with an initialiser.
        return {
            vdef.name: vdef.value
            for vdef in all_vars.values()
            if not isinstance(vdef.value, Variable)
        }

    def get_currently_visible_definitions(self) -> set[tuple[str, int]]:
        all_vars = self._get_all_visible_definitions()
        return {(vdef.name, vdef.revision) for vdef in all_vars.values()}

    def enter_scope(self, env_type: LocalEnvType) -> None:
        if env_type not in LOCAL_ENV_TYPES:
            raise ValueError("Attempted to enter a global environment")
        self._local_environment_stack.append(Environment(env_type))
        logger.debug(f"Entered {self.environment_stack[-1]}")

    def exit_scope(self) -> None:
        logger.debug(f"Leaving {self.environment_stack[-1]}")
        _ = self._local_environment_stack.pop()
