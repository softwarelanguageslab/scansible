# pyright: reportUnknownVariableType = false

"""Common Ansible directives (`vars`, `become`, `tags`, ...) shared by tasks, blocks, and plays."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, model_validator

from scansible.cst import YamlBool, YamlMap, YamlStr

from ..common import RawDirectives
from .expression import (
    AnyExpression,
    BoolLiteral,
    Expression,
    Identifier,
    IntLiteral,
    MapLiteral,
    SeqLiteral,
    StrLiteral,
)


class CommonDirectives(BaseModel, frozen=True):
    """Mixin for AST nodes that contain the common Ansible directives."""

    #: Name of a task, block, or play.
    name: StrLiteral | None = None

    #: The connection plugin to use in this task, block, or play.
    connection: StrLiteral | None = None
    #: Override default port in connection.
    port: IntLiteral | Expression | None = None
    #: Remote user name.
    remote_user: StrLiteral | None = None

    #: Variables defined on the entity.
    vars: MapLiteral[Identifier, AnyExpression] = Field(default_factory=MapLiteral)

    #: Specify default arguments to modules in this entity.
    module_defaults: SeqLiteral[
        MapLiteral[StrLiteral, MapLiteral[StrLiteral, AnyExpression]]
    ] = Field(default_factory=SeqLiteral)

    #: Dictionary converted into environment variables.
    environment: SeqLiteral[MapLiteral[StrLiteral, AnyExpression] | Expression] = Field(
        default_factory=SeqLiteral
    )
    #: To disable logging of action.
    no_log: BoolLiteral | Expression | None = None
    #: Run on a single host only.
    run_once: BoolLiteral | Expression | None = None
    #: Ignore task failures.
    ignore_errors: BoolLiteral | Expression | None = None
    #: Ignore task failures due to unreachable host.
    ignore_unreachable: BoolLiteral | Expression | None = None
    #: Toggle check mode (dry run).
    check_mode: BoolLiteral | Expression | None = None
    #: Toggle returning diff information from task.
    diff: BoolLiteral | Expression | None = None
    #: End play once one task fails for one host.
    any_errors_fatal: BoolLiteral | Expression | None = None
    #: Max amount of hosts to operate on in parallel.
    throttle: IntLiteral | Expression | None = None
    #: Task timeout.
    timeout: IntLiteral | Expression | None = None

    #: Set debugger state.
    debugger: StrLiteral | None = None

    #: Whether to perform privilege escalation.
    become: BoolLiteral | Expression | None = None
    #: How to perform privilege escalation (sudo, su, ...)
    become_method: Expression | StrLiteral | None = None
    #: User to escalate to.
    become_user: Expression | StrLiteral | None = None
    #: Flags to pass to privilege escalation program.
    become_flags: Expression | StrLiteral | None = None
    #: Path to privilege escalation executable.
    become_exe: Expression | StrLiteral | None = None

    #: Tags on the entity.
    tags: SeqLiteral[StrLiteral | IntLiteral] = Field(default_factory=SeqLiteral)
    #: List of collections to search for modules in this entity.
    collections: SeqLiteral[StrLiteral] = Field(default_factory=SeqLiteral)

    @model_validator(mode="before")
    @classmethod
    def _fallback_normalize(cls, value: object) -> object:
        """Perform fallback normalization of common directives.

        Some of this normalization was possibly already done by subclasses.
        """
        if not isinstance(value, dict):
            return value

        value = cast(RawDirectives, value.copy())
        return cls._normalize_common_directives(value)

    @classmethod
    def _normalize_common_directives(cls, ds: RawDirectives) -> RawDirectives:
        """Normalize common directives.

        Assumes that the provided data structure is a copy of the original and can be mutated.
        """
        ds = cls._transform_old_become(ds)
        ds = cls._transform_old_always_run(ds)
        return ds

    @classmethod
    def _transform_old_become(cls, ds: RawDirectives) -> RawDirectives:
        """Translate legacy `sudo`/`su` directives, and their derivatives, to `become`."""
        # Tasks that use sudo/su and their derivatives (*_user, *_exe, *_flags, *_pass) are no
        # longer supported in recent Ansible versions. Transform them like legacy Ansible versions used to do.
        # https://github.com/ansible/ansible/commit/e40832df847bc7dcc94f41c491618de665c0b9e5

        # Same validation as legacy Ansible versions
        has_become = "become" in ds or "become_user" in ds
        has_sudo = "sudo" in ds or "sudo_user" in ds
        has_su = "su" in ds or "su_user" in ds

        if not (has_sudo or has_su):
            # Nothing to transform.
            return ds

        # At most one become method may be present.
        if sum((has_become, has_sudo, has_su)) > 1:
            raise ValueError("Invalid mix of directives: sudo/su/become")

        prefix = "sudo" if has_sudo else "su"
        suffixes = ("", "_user", "_exe", "_flags", "_pass")

        # If sudo or su is specified as directive, we can mark those as the become-method.
        ds["become_method"] = YamlStr(prefix)

        # Transform each (derived) directive to use `become`.
        for suffix in suffixes:
            old_directive = f"{prefix}{suffix}"
            new_directive = f"become{suffix}"

            if suffix == "_pass" and old_directive in ds:
                # There's no `become_pass` alternative, so define the variable instead.
                variables = ds.get("vars", YamlMap())
                if not isinstance(variables, dict):
                    raise ValueError("Expected `vars` directive to carry a dictionary")
                variables[YamlStr("ansible_become_password")] = ds.pop(old_directive)
                ds["vars"] = variables
                continue

            if old_directive in ds:
                ds[new_directive] = ds.pop(old_directive)

        return ds

    @classmethod
    def _transform_old_always_run(cls, ds: RawDirectives) -> RawDirectives:
        """Translate the removed `always_run` directive to `check_mode`."""
        # `always_run` is an old, now-removed directive which has since been
        # replaced by the `check_mode: no` directive.
        if always_run := ds.pop("always_run", None):
            # if `always_run: yes` -> `check_mode: no`.
            # not sure if `always_run: no` necessarily means `check_mode: yes` or
            # just "use default behaviour".
            ds["check_mode"] = YamlBool(False, location=always_run.__location__)  # noqa: FBT003

        return ds
