from __future__ import annotations

from typing import TYPE_CHECKING, cast, final

from collections import defaultdict
from collections.abc import Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager

from ansible.module_utils.facts.system.distribution import (  # pyright: ignore[reportMissingTypeStubs]
    Distribution,
)
from loguru import logger

from scansible import ast
from scansible.pdg import representation as rep

from .environment import (
    EnvironmentStack,
    EnvironmentType,
    LocalEnvType,
    VariableDefinitionRecord,
)

if TYPE_CHECKING:
    from ...context import BuildContext


_DefRevisionMap = dict[str, int]


@final
class VariableManager:
    """Managers variable definitions and lookups."""

    def __init__(self, context: BuildContext) -> None:
        self._envs = EnvironmentStack()
        self.build_ctx = context
        self._next_def_revisions: _DefRevisionMap = defaultdict(lambda: 0)

    def _get_next_def_revision(self, var_name: str) -> int:
        self._next_def_revisions[var_name] += 1
        return self._next_def_revisions[var_name] - 1

    @contextmanager
    def enter_scope(self, env_type: LocalEnvType) -> Generator[None]:
        """Enter a new environment of the given type, yield, and exit automatically."""
        self._envs.enter_scope(env_type)
        yield
        self._envs.exit_scope()

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
        prior_version = self._get_prior_version(name)
        self._define_variable(
            name, revision, env_type, initialiser, conditions, prior_version
        )

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
        prior_version = self._get_prior_version(name)
        var_node = rep.Variable(
            name=name,
            version=revision,
            value_version=0,
            scope_level=env_type.value,
            prior_version=prior_version,
            location=self.build_ctx.get_location(name),
        )
        self.build_ctx.graph.add_node(var_node)
        for cond in conditions or []:
            self.build_ctx.graph.add_edge(cond, var_node, rep.WHEN)
        self._define_variable(
            name, revision, env_type, var_node, conditions, prior_version
        )
        return var_node

    def _get_prior_version(self, name: str) -> int | None:
        """Get the revision of the same-named definition currently visible, if any."""
        rec = self._envs.get_variable_definition(name)
        return rec.revision if rec is not None else None

    def _define_variable(
        self,
        name: str,
        revision: int,
        env_type: EnvironmentType,
        value: ast.AnyExpression | rep.Variable,
        conditions: Sequence[rep.DataNode] | None,
        prior_version: int | None,
    ) -> None:
        """Declare a variable, bound to the given value.

        The value is either an actual variable node, in case the variable is injected with an eagerly-evaluated
        value, or an expression to be lazily evaluated when the variable is dereferenced.
        """
        logger.debug(f"Defining variable {name!r} in env of type {env_type.name}")

        def_record = VariableDefinitionRecord(
            name,
            revision,
            value,
            env_type,
            tuple(conditions or []),
            self.build_ctx.get_location(name),
            prior_version,
        )
        self._envs.set_variable_definition(def_record)

    def lookup_variable(self, name: str) -> VariableDefinitionRecord | None:
        """Look up and return the highest precedence variable definition for the given name, or None if not defined."""
        return self._envs.get_variable_definition(name)

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
