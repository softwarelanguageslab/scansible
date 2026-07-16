"""AST nodes for playbooks and the plays they contain."""

from __future__ import annotations

from typing import Annotated, Literal, cast, override

from collections.abc import Sequence

from pydantic import Discriminator, Field, Tag, field_validator, model_validator

from scansible.types import AnyValue
from scansible.utils import ProjectPath
from scansible.utils.actions import is_import_playbook

from .._normalizers import Lenient, Listify
from .._validators import Identifier
from ..common import ExtractionContext, RawDirectives, parse_file
from .base import ASTFile, ASTNode
from .directives import CommonDirectives
from .expression import Condition, Expression
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
    tasks: Annotated[Sequence[TaskOrBlock], Lenient] = Field(default_factory=tuple)

    #: Whether to gather facts from the remote hosts.
    gather_facts: bool | Expression | None = None

    #: Subset of facts to gather from remote hosts.
    gather_subset: Annotated[Sequence[str], Listify] = Field(default_factory=tuple)
    #: Timeout for fact gathering.
    gather_timeout: int | Expression | None = None
    #: Fact path option for fact gathering.
    fact_path: str | None = None

    #: List of files with variables to include into play.
    vars_files: Sequence[Sequence[str]] = Field(default_factory=tuple)
    #: List of variables to prompt user for. List of mappings, `name` key
    #: contains variable name.
    vars_prompt: Annotated[Sequence[VarsPrompt], Listify] = Field(default_factory=tuple)

    #: List of roles to be imported into play.
    roles: Annotated[Sequence[PlayRoleRequirement], Lenient] = Field(
        default_factory=tuple
    )

    #: Handlers for the play.
    handlers: Annotated[Sequence[Handler], Lenient] = Field(default_factory=tuple)
    #: Tasks to be run before the roles in `roles`.
    pre_tasks: Annotated[Sequence[TaskOrBlock], Lenient] = Field(default_factory=tuple)
    #: Tasks to be run after the main tasks.
    post_tasks: Annotated[Sequence[TaskOrBlock], Lenient] = Field(default_factory=tuple)

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

        value = cls._normalize_user(value)

        return value

    @classmethod
    def _normalize_user(cls, ds: RawDirectives) -> RawDirectives:
        """Normalize the deprecated `user` directive to `remote_user`"""
        if "user" not in ds:
            return ds

        if "remote_user" in ds:
            raise ValueError("`user` and `remote_user` are mutually exclusive")

        ds["remote_user"] = ds.pop("user")
        return ds

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


class ImportPlaybook(ASTNode, CommonDirectives, frozen=True):
    """Represents import_playbook Ansible tasks present in a playbook at the top level."""

    import_playbook: str
    when: Annotated[Sequence[Condition | bool], Listify] = Field(default_factory=tuple)

    @model_validator(mode="before")
    @classmethod
    def _normalize_keyword(cls, value: object) -> object:
        """Normalize fully-qualified `import_playbook` action name."""
        if not isinstance(value, dict):
            return value

        value = cast(dict[object, object], value.copy())
        for fqn in (
            "ansible.builtin.import_playbook",
            "ansible.legacy.import_playbook",
        ):
            if fqn not in value:
                continue
            if "import_playbook" in value:
                raise ValueError("Conflicting `import_playbook` directives")
            value["import_playbook"] = value.pop(fqn)

        return value


def _distinguish_import_vs_play(obj: object) -> Literal["import", "play"] | None:
    if isinstance(obj, dict):
        if any(
            isinstance(key, str) and is_import_playbook(key)
            for key in cast(dict[object, object], obj)
        ):
            return "import"
        return "play"
    if isinstance(obj, Play):
        return "play"
    if isinstance(obj, ImportPlaybook):
        return "import"

    raise ValueError("Expected import_playbook and play to be a dictionary")


#: A playbook entry: either a `Play` or an `ImportPlaybook`.
#: `ImportPlaybook` takes precedence: If an `import_playbook` is present,
#: it should be parsed as an `ImportPlaybook` instead of a `Play`.
type PlaybookChild = Annotated[
    Annotated[ImportPlaybook, Tag("import")] | Annotated[Play, Tag("play")],
    Discriminator(_distinguish_import_vs_play),
]


class Playbook(ASTFile, frozen=True):
    """Represents an Ansible playbook."""

    #: List of plays defined in this playbook.
    plays: Annotated[Sequence[PlaybookChild], Lenient]

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> Playbook:
        """Load and parse a playbook from the given path."""
        return cls.model_validate(
            {"path": path.relative, "plays": parse_file(path)}, context=context
        )
