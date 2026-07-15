"""AST nodes for playbooks and the plays they contain."""

from __future__ import annotations

from typing import Annotated, cast, override

from collections.abc import Sequence

from pydantic import Field, field_validator, model_validator

from scansible.types import AnyValue
from scansible.utils import ProjectPath

from .._normalizers import Lenient, Listify, NormalizeNone
from .._validators import Identifier
from ..common import ExtractionContext, RawDirectives, parse_file
from .base import ASTFile, ASTNode
from .directives import CommonDirectives
from .expression import Expression
from .role_meta import RoleRequirement
from .task import Handler, TaskOrBlock


class VarsPrompt(ASTNode, frozen=True):
    """Represents a vars_prompt entry."""

    #: Name of the variable.
    name: Identifier
    #: Prompt to show.
    prompt: str | None = None
    #: Default value.
    default: AnyValue | None = None
    #: Whether to hide the input on the terminal (e.g. for passwords).
    private: bool | Expression | None = None
    #: Whether the user needs to re-enter to confirm.
    confirm: bool | Expression = False
    #: Encryption algorithm to use on the value.
    encrypt: str | None = None
    #: Salt size to use in encryption.
    salt_size: int | Expression | None = None
    #: Salt to use in encryption.
    salt: str | None = None
    #: Whether the user input is unsafe and should not be templated.
    unsafe: bool | Expression | None = None


class PlayRoleRequirement(RoleRequirement, frozen=True):
    """Represents a role dependency specified in a play's `roles` directive."""

    @model_validator(mode="before")
    @classmethod
    def _parse_from_string(cls, value: object) -> object:
        """Normalize a bare string/int role reference into `{"role": ...}`."""
        # Ansible coerces int to str here, we'll do it too.
        if isinstance(value, int):
            value = str(value)

        if not isinstance(value, str):
            return value

        return {"role": value}


class Play(ASTNode, CommonDirectives, frozen=True):
    """Represents an Ansible play contained within a playbook."""

    #: The play's targetted hosts.
    hosts: Annotated[Sequence[str], Listify]
    #: The play's list of blocks.
    tasks: Sequence[TaskOrBlock] = Field(default_factory=tuple)

    #: Whether to gather facts from the remote hosts.
    gather_facts: bool | Expression | None = None

    #: Subset of facts to gather from remote hosts.
    gather_subset: Annotated[Sequence[str], Listify] = Field(default_factory=tuple)
    #: Timeout for fact gathering.
    gather_timeout: int | Expression | None = None
    #: Fact path option for fact gathering.
    fact_path: str | None = None

    #: List of files with variables to include into play.
    vars_files: Annotated[Sequence[Sequence[str]], NormalizeNone] = Field(
        default_factory=tuple
    )
    #: List of variables to prompt user for. List of mappings, `name` key
    #: contains variable name.
    vars_prompt: Annotated[Sequence[VarsPrompt], Listify] = Field(default_factory=tuple)

    #: List of roles to be imported into play.
    roles: Sequence[PlayRoleRequirement] = Field(default_factory=tuple)

    #: Handlers for the play.
    handlers: Sequence[Handler] = Field(default_factory=tuple)
    #: Tasks to be run before the roles in `roles`.
    pre_tasks: Sequence[TaskOrBlock] = Field(default_factory=tuple)
    #: Tasks to be run after the main tasks.
    post_tasks: Sequence[TaskOrBlock] = Field(default_factory=tuple)

    #: Force handler notification.
    force_handlers: bool | Expression | None = None
    #: Maximum percentage of hosts that are allowed to fail before aborting play.
    max_fail_percentage: int | float | Expression | None = None
    #: Define how Ansible batches execution on hosts.
    serial: Annotated[Sequence[str | int], Listify] = Field(default_factory=tuple)
    #: Execution strategy related to parallel host execution.
    strategy: str | None = None
    #: How hosts should be sorted in execution order.
    order: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_play(cls, value: object) -> object:
        """Perform normalization of play directives."""
        if not isinstance(value, dict):
            return value

        value = cast(RawDirectives, value.copy())

        # remove the "accelerate" key if present. It was removed in 2.4
        _ = value.pop("accelerate", None)

        return value

    @field_validator("vars_files", mode="before")
    @classmethod
    def _normalize_vars_files(cls, value: object) -> object:
        """Normalize vars_files into nested sequences."""
        if not isinstance(value, Sequence) or isinstance(value, str):
            value = [value]
        new_value = []
        for entry in value:
            if not isinstance(entry, Sequence) or isinstance(entry, str):
                entry = [entry]
            new_value.append(entry)  # pyright: ignore[reportUnknownMemberType]
        return new_value  # pyright: ignore[reportUnknownVariableType]

    @field_validator("hosts", mode="after")
    @classmethod
    def _validate_hosts(cls, value: Sequence[str]) -> Sequence[str]:
        """Validate the value of the `hosts` field."""
        if not value:
            raise ValueError("Play `hosts` cannot be empty")
        return value


class Playbook(ASTFile, frozen=True):
    """Represents an Ansible playbook."""

    #: List of plays defined in this playbook.
    plays: Annotated[Sequence[Play], Lenient]

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> Playbook:
        """Load and parse a playbook from the given path."""
        return cls.model_validate(
            {"path": path.relative, "plays": parse_file(path)}, context=context
        )
