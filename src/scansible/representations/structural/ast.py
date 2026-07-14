"""AST node representations."""

# pyright: reportUnknownVariableType = false

# FIXME!!! Source code position information is largely broken due to Pydantic coercing Ansible types (AnsibleUnicode, AnsibleMapping, ...)
# to plain data types (str, dict, ...), losing the custom `ansible_pos` field.

from __future__ import annotations

from typing import (
    Annotated,
    Callable,
    ClassVar,
    Literal,
    Self,
    cast,
    get_args,
    get_origin,
    override,
)

import keyword
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping, Sequence
from functools import cached_property
from pathlib import Path

from ansible.parsing.splitter import parse_kv, split_args
from ansible.utils.fqcn import add_internal_fqcns
from pydantic import (
    AfterValidator,
    BaseModel,
    Discriminator,
    Field,
    PositiveInt,
    StringConstraints,
    Tag,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.fields import FieldInfo

from scansible.representations.structural.helpers import (
    ProjectPath,
    find_all_files,
    find_file,
    parse_file,
)
from scansible.types import AnyValue, ScalarValue
from scansible.utils import FrozenDict, actions

# Adapted from ansible.constants
FREEFORM_ACTIONS_SIMPLE = (
    "command",
    "raw",
    "script",
    "shell",
    "win_command",
    "win_shell",
)
FREEFORM_ACTIONS = frozenset(
    tuple(add_internal_fqcns(FREEFORM_ACTIONS_SIMPLE))
    + ("ansible.windows.win_command", "ansible.windows.win_shell")
)


def _validate_relative_path(path: Path) -> Path:
    """Validate whether the given path is a relative path.

    Note that we do not validate whether it is relative to any particular
    directory.
    """
    if path.is_absolute():
        raise ValueError(f"Expected relative path, got {path}")
    return path


def _validate_absolute_path(path: Path) -> Path:
    """Validate whether the given path is an absolute path."""
    if not path.is_absolute():
        raise ValueError(f"Expected absolute path, got {path}")
    return path


def _validate_identifier(value: str) -> str:
    """Validate whether the given value is a valid identifier.

    Logic mirrors Ansible's own logic in `ansible.utils.vars.isidentifier`.
    """
    if not (value.isascii() and value.isidentifier()):
        raise ValueError(f"Expected a valid identifier, got {value}")
    if keyword.iskeyword(value):
        raise ValueError(f"{value} is a reserved keyword")
    return value


#: Relative paths in the project
type RelativePath = Annotated[Path, AfterValidator(_validate_relative_path)]

#: Absolute paths in the project
type AbsolutePath = Annotated[Path, AfterValidator(_validate_absolute_path)]

type Identifier = Annotated[str, AfterValidator(_validate_identifier)]


class ExtractionContext:
    """Context during extraction, to store broken files etc."""

    #: Whether extraction should be lenient. If true, the extractor will skip
    #: tasks or blocks that fail to extract, without skipping the entire file.
    #: If false, the entire file will be skipped instead.
    lenient: bool
    #: List of broken files which could not be parsed/extracted.
    broken_files: list[BrokenFile]
    #: List of broken tasks or blocks that could not be parsed/extracted.
    broken_tasks: list[BrokenTask]

    def __init__(self, lenient: bool) -> None:
        self.lenient = lenient
        self.broken_files = []
        self.broken_tasks = []


class Normalizer(ABC):
    """Normalization logic for AST models."""

    @classmethod
    @abstractmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        """Perform the normalization."""
        raise NotImplementedError


class NormalizeNone(Normalizer):
    """Normalizer that normalizes `None` values to the field's default."""

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if value is not None:
            return value

        return field_info.get_default(call_default_factory=True, validated_data=value)  # pyright: ignore[reportAny]


class Listify(Normalizer):
    """Normalizer that normalizes single values to a list of that value."""

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if isinstance(value, Sequence) and not isinstance(value, str):
            return value

        return [value]


class Stringify(Normalizer):
    """Normalizer that normalizes non-string values to stringified values.

    By default, it only normalizes int, float, and bool values, and recursively normalizes
    entries in lists.
    """

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if isinstance(value, str):
            return value

        if isinstance(value, (int, float, bool)):
            return str(value)

        if isinstance(value, Sequence):
            return type(value)(
                (
                    cls.normalize(element, field_info, validation_info)
                    for element in value
                )  # pyright: ignore[reportCallIssue]
            )

        return value


class Lenient(Normalizer):
    """Normalizer that enables parsing in sequences to be lenient.

    If the lenient flag is set in the validation context, this normalizer will catch
    any item-specific validation errors and ignore it, omitting that item from the
    resulting list. In non-lenient (strict) mode, the validator acts normally.
    """

    @classmethod
    def _get_contained_type(cls, field_info: FieldInfo) -> type[object]:
        annotation = field_info.annotation

        if (
            annotation is None
            or (origin := get_origin(annotation)) is None
            or not issubclass(origin, Sequence)
        ):
            raise ValueError("Can only mark Sequences as Lenient")

        return get_args(annotation)[0]  # pyright: ignore[reportAny]

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if not isinstance(value, Sequence):
            return value

        if validation_info.context is None:
            return value

        if not isinstance(validation_info.context, ExtractionContext):  # pyright: ignore[reportAny]
            raise ValueError("Expected context to be an ExtractionContext")

        context = validation_info.context
        if not context.lenient:
            return value

        contained_type = cls._get_contained_type(field_info)
        adapter = TypeAdapter[ASTEntity](contained_type)

        results: list[ASTEntity] = []
        for raw in value:
            try:
                results.append(
                    adapter.validate_python(raw, context=validation_info.context)  # pyright: ignore[reportArgumentType] -- bad type defs?
                )
            except ValidationError as exc:
                context.broken_tasks.append(BrokenTask(raw=raw, reason=str(exc)))

        return results


#: Raw Ansible position tuple, with validation logic.
type RawPosition = tuple[
    Annotated[str, StringConstraints(strict=True, min_length=1)],
    PositiveInt,
    PositiveInt,
]

RawPositionAdapter = TypeAdapter(RawPosition)


class Position(BaseModel, strict=True, frozen=True, extra="forbid"):
    """Code position of an AST node."""

    # TODO: Should this be a RelativePath instead?
    file: Path = Path("unknown file")
    start_line: PositiveInt = -1
    start_column: PositiveInt = -1

    @property
    def is_synthetic(self) -> bool:
        return self.start_line < 0

    @model_validator(mode="before")
    def _coerce_from_ansible_position(cls, value: object) -> object:
        try:
            file, line, column = cast(
                RawPosition, RawPositionAdapter.validate_python(value)
            )
        except ValidationError:
            return value
        return {"file": Path(file), "start_line": line, "start_column": column}


class ASTEntity(BaseModel, strict=True, frozen=True, extra="forbid"):
    """Base class inherited by all classes participating in the AST representation."""

    @field_validator("*", mode="before")
    @classmethod
    def _normalize(cls, value: object, info: ValidationInfo) -> object:
        """Apply the declared normalizations to field values."""

        assert info.field_name is not None
        field_info = cls.model_fields[info.field_name]

        for meta in field_info.metadata:  # pyright: ignore[reportAny]
            if isinstance(meta, Normalizer) or (
                isinstance(meta, type) and issubclass(meta, Normalizer)
            ):
                value = meta.normalize(value, field_info, info)

        return value


class ASTFile(ASTEntity, ABC, frozen=True):
    """Base class inherited by all files represented by an AST."""

    #: The relative path to the file in the project.
    path: RelativePath

    @classmethod
    @abstractmethod
    def load(cls: type[Self], path: ProjectPath, context: ExtractionContext) -> Self:
        """Construct the representation for a file by parsing the given path."""
        ...


class ASTNode(ASTEntity, frozen=True):
    """Base class inherited by all nodes inside of an AST for a file."""

    #: The source code position of the node.
    position: Position = Field(default_factory=Position)

    @model_validator(mode="before")
    @classmethod
    def _inject_position(cls, data: object) -> object:
        """Extract sourec code position information from Ansible objects and present it to the model for validation."""

        if hasattr(data, "ansible_pos"):
            pos = getattr(data, "ansible_pos")  # pyright: ignore[reportAny]
            if isinstance(data, dict):
                data["position"] = pos

        return data


class BrokenTask(ASTEntity, frozen=True):
    """Represents a task/block that could not be extracted."""

    #: The raw datastructure that failed to extract.
    raw: object
    #: The reason for failure.
    reason: str


class BrokenFile(ASTFile, frozen=True):
    """Represents a file that could not be parsed or extracted."""

    #: The reason for failure.
    reason: str

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> BrokenFile:
        raise NotImplementedError("Cannot load a broken file.")


type RawDirectives = dict[str, AnyValue]


class _CommonDirectives(BaseModel, frozen=True):
    """Mixin for AST nodes that contain the common Ansible directives."""

    #: Name of a task, block, or play.
    name: str | None = None

    #: The connection plugin to use in this task, block, or play.
    connection: str | None = None
    #: Override default port in connection.
    port: int | None = None
    #: Remote user name.
    remote_user: str | None = None

    #: Variables defined on the entity.
    vars: Mapping[Identifier, AnyValue] = Field(default_factory=FrozenDict)

    #: Specify default arguments to modules in this entity.
    module_defaults: Sequence[Mapping[str, Mapping[str, AnyValue]]] | None = None

    #: Dictionary converted into environment variables.
    environment: Sequence[Mapping[str, str] | str] | None = None
    #: To disable logging of action.
    no_log: bool | str | None = None
    #: Run on a single host only.
    run_once: bool | str | None = None
    #: Ignore task failures.
    ignore_errors: bool | str | None = None
    #: Ignore task failures due to unreachable host.
    ignore_unreachable: bool | str | None = None
    #: Toggle check mode (dry run).
    check_mode: bool | str | None = None
    #: Toggle returning diff information from task.
    diff: bool | str | None = None
    #: End play once one task fails for one host.
    any_errors_fatal: bool | str | None = None
    #: Max amount of hosts to operate on in parallel.
    throttle: str | int | None = None
    #: Task timeout.
    timeout: str | int | None = None

    #: Set debugger state.
    debugger: str | None = None

    #: Whether to perform privilege escalation.
    become: str | bool | None = None
    #: How to perform privilege escalation (sudo, su, ...)
    become_method: str | None = None
    #: User to escalate to.
    become_user: str | None = None
    #: Flags to pass to privilege escalation program.
    become_flags: str | None = None
    #: Path to privilege escalation executable.
    become_exe: str | None = None

    #: Tags on the entity.
    tags: Sequence[str | int] = Field(default_factory=tuple)
    #: List of collections to search for modules in this entity.
    collections: Sequence[str] = Field(default_factory=tuple)

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
        ds["become_method"] = prefix

        # Transform each (derived) directive to use `become`.
        for suffix in suffixes:
            old_directive = f"{prefix}{suffix}"
            new_directive = f"become{suffix}"

            if suffix == "_pass" and old_directive in ds:
                # There's no `become_pass` alternative, so define the variable instead.
                variables = ds.get("vars", {})
                if not isinstance(variables, dict):
                    raise ValueError("Expected `vars` directive to carry a dictionary")
                variables["ansible_become_password"] = ds.pop(old_directive)
                ds["vars"] = variables
                continue

            if old_directive in ds:
                ds[new_directive] = ds.pop(old_directive)

        return ds

    @classmethod
    def _transform_old_always_run(cls, ds: RawDirectives) -> RawDirectives:
        # `always_run` is an old, now-removed directive which has since been
        # replaced by the `check_mode: no` directive.
        if "always_run" in ds:
            # if `always_run: yes` -> `check_mode: no`.
            # not sure if `always_run: no` necessarily means `check_mode: yes` or
            # just "use default behaviour".
            if ds.pop("always_run"):
                ds["check_mode"] = False

        return ds


class Platform(ASTNode, frozen=True):
    """Represents a platform supported by a role, as denoted in the meta file."""

    #: Platform name.
    name: str
    #: Platform version.
    version: str = Field(strict=False)


class _RawPlatform(ASTNode, frozen=True):
    """Intermediate Platform representation with a list of versions."""

    #: Platform name.
    name: str
    #: Platform versions.
    versions: Annotated[
        Sequence[Annotated[str, Field(strict=False)]], Stringify, Listify
    ]

    def expand(self) -> Sequence[Platform]:
        """Expand a single raw platform instance to a flattened list of platforms."""
        return [
            Platform(name=self.name, version=version, position=self.position)
            for version in self.versions
        ]


class RoleRequirement(ASTNode, _CommonDirectives, frozen=True):
    """Represents a role inclusion dependency.

    These occur in a play's `roles` directive or a role's `dependencies`, see concrete subclasses.
    """

    #: The role that is depended upon.
    role: str

    #: The role include parameters.
    params: Mapping[str, AnyValue] = Field(default_factory=FrozenDict)

    #: Delegate execution to another host.
    delegate_to: str | None = None
    #: Apply facts to delegated host.
    delegate_facts: str | bool | None = None

    #: Optional condition on when to include a dependency.
    when: Annotated[Sequence[str | bool], Listify] = Field(default_factory=tuple)

    @field_validator("role", mode="after")
    def _validate_role_name(cls, value: str) -> str:
        # Commas in role names are only allowed in meta/main.yml dependencies, and should have
        # been filtered out/converted already.
        if "," in value:
            raise ValueError(f"Invalid old-style role requirement: {value}")
        return value

    @model_validator(mode="before")
    @classmethod
    def _extract_parameters(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        valid_attr_names = cls.model_fields.keys()
        new_value = {"params": {}}
        for k, v in value.items():
            if k in valid_attr_names:
                new_value[k] = v
            else:
                new_value["params"][k] = v
        return new_value


class PlayRoleRequirement(RoleRequirement, frozen=True):
    """Represents a role dependency specified in a play's `roles` directive."""

    @model_validator(mode="before")
    @classmethod
    def _parse_from_string(cls, value: object) -> object:
        # Ansible coerces int to str here, we'll do it too.
        if isinstance(value, int):
            value = str(value)

        if not isinstance(value, str):
            return value

        return {"role": value}


class MetaRoleRequirement(RoleRequirement, frozen=True):
    """Represents a role dependency specified in a role's `meta/main.yml` file.

    These differ from play-level dependencies as the role can be specified with the Ansible Galaxy
    notation found in requirements.yml, and thus require specialised parsing.
    """

    @model_validator(mode="before")
    @classmethod
    def _parse(cls, value: object) -> object:
        """Parse the AST from the raw YAML specification."""

        # Need to make sure these run in the correct order.
        value = cls._parse_from_string(value)
        value = cls._extract_role_name(value)
        return value

    @classmethod
    def _parse_from_string(cls, value: object) -> object:
        # Ansible coerces int to str here, we'll do it too.
        if isinstance(value, int):
            value = str(value)

        if not isinstance(value, str):
            return value

        # Normalize to new-style role dependency if the raw string contains a comma, otherwise to an old-style
        # dependency. Validation as per `ansible.playbook.role.requirement`.
        match value.split(","):
            case [src, version, name]:
                return {"src": src, "version": version, "name": name}
            case [src, version]:
                return {"src": src, "version": version}
            case [src]:
                return {"src": src}
            case _:
                raise ValueError(
                    f"Invalid role line: {value}. Proper format is 'src[,version[,name]]'"
                )

    @classmethod
    def _extract_role_name(cls, value: object) -> object:
        if not isinstance(value, dict) or "role" in value:
            return value

        # Omit role soure info
        new_value = {
            k: v for k, v in value.items() if k not in ("src", "version", "scm")
        }

        if "name" in value:
            new_value["role"] = value["name"]
        elif "src" in value:
            src = value["src"]
            if not isinstance(src, str):
                raise ValueError(
                    "Expected `src` in new-style role requirement to be a str"
                )

            # Extraction per ansible.playbook.role.requirement.
            name = (
                src.split("/")[-1]
                .removesuffix(".git")
                .removesuffix(".tar.gz")
                .split(",")[0]
            )
            new_value["role"] = name
        else:
            raise ValueError("Expected `src` or `name` in new-style role requirement")

        return new_value


class MetaBlock(ASTNode, frozen=True, extra="ignore"):
    """Represents a role metadata block."""

    #: Platforms supported by the role
    platforms: Annotated[Sequence[Platform], Listify] = Field(default_factory=tuple)
    #: Role dependencies
    dependencies: Annotated[Sequence[MetaRoleRequirement], Lenient] = Field(
        default_factory=tuple
    )

    @field_validator("platforms", mode="before")
    @classmethod
    def _convert_platforms(cls, value: object) -> object:
        """Convert the platforms list into a consistent schema before validation."""

        assert isinstance(value, list)  # Should be covered by the Listify marker.
        raw_platforms = [_RawPlatform.model_validate(platform) for platform in value]
        return [
            platform
            for raw_platform in raw_platforms
            for platform in raw_platform.expand()
        ]

    @model_validator(mode="before")
    @classmethod
    def _hoist_platforms(cls, value: object) -> object:
        """Hoist `galaxy_info.platforms` to a top-level key before validation."""

        if isinstance(value, dict) and "galaxy_info" in value:
            if not isinstance(value["galaxy_info"], dict):
                raise ValueError("Expected `galaxy_info` to be a dict")
            if "platforms" in value["galaxy_info"]:
                value["platforms"] = value["galaxy_info"]["platforms"]

        return value


class MetaFile(ASTFile, frozen=True):
    """Represents a file containing role metadata."""

    #: The metadata block contained in the file.
    metablock: MetaBlock

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> MetaFile:
        return cls.model_validate(
            {"path": path.relative, "metablock": parse_file(path)}, context=context
        )


class VariableFile(ASTFile, frozen=True):
    """Represents a file containing variables."""

    #: The variables contained within the file. The order is irrelevant.
    variables: Annotated[Mapping[Identifier, AnyValue], NormalizeNone] = Field(
        default_factory=dict
    )

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> VariableFile:
        return cls.model_validate(
            {"path": path.relative, "variables": parse_file(path)}, context=context
        )


class LoopControl(ASTNode, frozen=True):
    """Represents the loop control directive value."""

    #: The loop variable name. `item` by default.
    loop_var: Identifier = "item"
    #: The index variable name.
    index_var: Identifier | None = None
    #: Loop label in output. Should technically be a string only, but Ansible
    #: doesn't complain about dicts and just templates and stringifies those.
    label: AnyValue = None
    #: Amount of time in seconds to pause between each iteration. Can be a
    #: string in case this is an expression. 0 by default.
    pause: str | int | float = 0.0
    #: Whether to include more information in the loop items.
    #: See https://docs.ansible.com/ansible/latest/user_guide/playbooks_loops.html#extended-loop-variables
    extended: str | bool | None = None
    #: Whether to include `allitems` in the extended version.
    extended_allitems: str | bool | None = True
    #: Conditions when to break the loop
    break_when: Sequence[str] | None = Field(default_factory=tuple)


class BaseTask(ASTNode, _CommonDirectives, frozen=True):
    """Represents commonalities for Ansible tasks."""

    VALID_INCLUDE_DIRECTIVES: ClassVar[frozenset[str]] = frozenset(
        (
            "action",
            "args",
            "collections",
            "debugger",
            "ignore_errors",
            "loop",
            "loop_control",
            "loop_with",
            "name",
            "no_log",
            "register",
            "run_once",
            "tags",
            "timeout",
            "vars",
            "when",
        )
    )

    #: Action of the task.
    action: str
    #: Arguments to the action.
    args: Mapping[str, AnyValue]

    #: Run task asynchronously for at most the given number of seconds.
    async_val: str | int | None = 0
    #: Conditional expression(s) to override "changed" status.
    changed_when: Annotated[Sequence[str | bool], Listify] = Field(
        default_factory=tuple
    )
    #: Number of seconds to delay between retries.
    delay: str | float | int | None = 5.0
    #: Delegate task execution to another host.
    delegate_to: str | None = None
    #: Apply facts to delegated host.
    delegate_facts: str | bool | None = None
    #: Conditional expression(s) to override the "failed" status.
    failed_when: Annotated[Sequence[str | bool], Listify] = Field(default_factory=tuple)
    #: Loop on the task, or None if no loop. Can be a string (an expression),
    #: a list of arbitrary values, or, when the loop comes from `with_dict`, a
    #: dict of arbitrary items.
    loop: str | Sequence[AnyValue] | Mapping[ScalarValue, AnyValue] | None = None
    #: The type of loop used in old looping syntax (`with_*`), e.g.
    #: `with_items` -> `items`.
    loop_with: str | None = None
    #: Loop control defined on the task.
    loop_control: LoopControl | None = None
    #: List of handler names of handlers to notify.
    notify: Sequence[str] | None = None
    #: Polling interval for async tasks.
    poll: str | int | None = None
    #: Value given to the register keyword, i.e. variable name that will store
    #: the result of this action. Renamed due to naming conflicts with base classes.
    # FIXME: Distinguish between expr and identifier.
    register_var: Identifier | str | None = Field(default=None, alias="register")
    #: Number of tries for failed tasks.
    retries: str | int | None = None
    #: Retry task until condition(s) are satisfied.
    until: Annotated[Sequence[str | bool], Listify] = Field(default_factory=tuple)
    #: Condition on the task, or None if no condition.
    when: Annotated[Sequence[str | bool], NormalizeNone, Listify] = Field(
        default_factory=tuple
    )

    @field_validator("action", mode="after")
    @classmethod
    def _reject_import_playbook(cls, action: str) -> str:
        """Reject import_playbook actions that are not top-level in a playbook."""
        # This AST node only gets constructed for tasks in task lists, so an
        # import_playbook is illegal here.
        if actions.is_import_playbook(action):
            raise ValueError(
                "import_playbook is only allowed as a top-level playbook task"
            )
        return action

    @model_validator(mode="before")
    @classmethod
    def _normalize_task(cls, value: object) -> object:
        """Perform normalization of task directives."""
        if not isinstance(value, dict):
            return value

        value = cast(RawDirectives, value.copy())
        value = cls._normalize_common_directives(value)
        value = cls._parse_task_action(value)
        value = cls._transform_includes(value)
        value = cls._transform_loop(value)
        value = cls._validate_include_directives(value)

        return value

    @classmethod
    def _parse_task_action(cls, ds: RawDirectives) -> RawDirectives:
        """Parse module action from a task.

        After successful invocation, the result is guaranteed to contain an `action` key.
        Parsing logic mirrors Ansible's own logic as specified in ModuleArgsParser.
        """
        if "action" in ds and "local_action" in ds:
            raise ValueError("action and local_action are mutually exclusive")

        # We distinguish between two styles:
        # - Old style: Using `action: xyz` or `local_action: xyz`
        # - New style: Using `xyz: args`
        old_style = True
        if "local_action" in ds:
            ds["action"] = ds.pop("local_action")
            # This unconditionally overrides any other delegation set.
            ds["delegate_to"] = "localhost"

        # Find action from unrecognized directives
        for k in list(ds.keys()):
            if cls._is_task_directive(k):
                continue
            if "action" in ds:
                raise ValueError(
                    f"Conflicting action statements: {k} vs {ds['action']}"
                )
            old_style = False
            ds["action"] = k

        if "action" not in ds:
            raise ValueError("No action found in task")

        # Parse the arguments, depending on whether they're old style or new style.
        if old_style:
            ds = cls._parse_old_style_module_arguments(ds)
        else:
            ds = cls._parse_new_style_module_arguments(ds)

        return ds

    @classmethod
    def _parse_old_style_module_arguments(cls, ds: RawDirectives) -> RawDirectives:
        """Parse arguments from an old-style task variant.

        - action: shell echo hi
        - action: copy src=a dest=b
        - action:
            module: copy
            args:
              src: a
              dest: b
        - action:
            module: copy
            src: a
            dest: b
        """
        # args have lower priority than specially-parsed arguments on the action.
        # Add from lowest to highest priority, will be combined at the end.
        arg_list: list[AnyValue] = [cls._parse_task_level_args(ds)]
        action = ds.pop("action")

        if isinstance(action, dict):
            # action is like { module: "xyz", a: b, ... }
            if "module" not in action:
                raise ValueError("No action detected in old-style task")
            args = action
            action = args.pop("module")
            arg_list.append(args)
            if "args" in args:
                # { module: "xyz", args: { ... }}
                arg_list.append(args.pop("args"))

        if not isinstance(action, str):
            raise ValueError("Expected action to be a string")

        # action is now for sure like "xyz" or "xyz a=b c=d"
        assert isinstance(action, str)
        [action, *action_args] = split_args(action)
        ds["action"] = action
        arg_list.append(" ".join(action_args))

        ds["args"] = cls._combine_args(action, *arg_list)

        return ds

    @classmethod
    def _parse_new_style_module_arguments(cls, ds: RawDirectives) -> RawDirectives:
        """Parse arguments from a new-style task variant.

        - shell: echo hi
        - shell: echo hi
          args:
            chdir: /
        - copy:
            src: a
            dest: b
        - copy: src=a dest=b
        """
        # args have lower priority than specially-parsed arguments on the action
        task_args = cls._parse_task_level_args(ds)
        action = cast(str, ds["action"])
        action_args = ds.pop(action)

        ds["args"] = cls._combine_args(action, task_args, action_args)

        return ds

    @classmethod
    def _parse_args(cls, action: str, args: str) -> Mapping[ScalarValue, AnyValue]:
        check_raw = action in FREEFORM_ACTIONS
        return parse_kv(args, check_raw)  # pyright: ignore[reportReturnType]

    @classmethod
    def _parse_task_level_args(
        cls, ds: RawDirectives
    ) -> Mapping[ScalarValue, AnyValue]:
        task_args = ds.pop("args", {})
        if isinstance(task_args, str):
            task_args = {"_variable_params": task_args}
        return task_args  # pyright: ignore[reportReturnType]

    @classmethod
    def _combine_args(cls, action: str, *arg_list: AnyValue) -> AnyValue:
        combined_args = {}
        for args in arg_list:
            if isinstance(args, str):
                args = cls._parse_args(action, args)
            if args is None:
                args = {}
            if not isinstance(args, dict):
                raise ValueError("Expected args to be a dictionary")
            combined_args.update(args)  # pyright: ignore[reportUnknownMemberType]

        return combined_args

    @classmethod
    def _is_task_directive(cls, key: str) -> bool:
        return (
            key in cls.model_fields
            or key == "static"
            or key == "register"  # Aliased in model_fields
            or key.startswith("with_")
        )

    @classmethod
    def _transform_includes(cls, ds: RawDirectives) -> RawDirectives:
        """Transform bare `include` actions and the `static` directive."""
        if "static" in ds:
            is_static = bool(ds.pop("static"))
        else:
            is_static = None

        action = ds["action"]
        assert isinstance(action, str)

        if actions.is_bare_include(action):
            # FIXME: If static is not explicitly set, Ansible will attempt to
            # figure out whether the inclusion is static or dynamic based on
            # context and based on whether the file exists, and fall back to
            # dynamic inclusion if that fails. This may lead to slightly different
            # semantics than our approximation here.
            ds["action"] = "import_tasks" if is_static else "include_tasks"
        elif actions.is_include_tasks(action) and is_static is True:
            raise ValueError("include_tasks with static: yes")
        elif actions.is_import_tasks(action) and is_static is False:
            raise ValueError("import_tasks with static: no")

        return ds

    @classmethod
    def _transform_loop(cls, ds: RawDirectives) -> RawDirectives:
        for k in set(ds):
            if not k.startswith("with_"):
                continue
            loop_name = k.removeprefix("with_")
            if "loop" in ds or "loop_with" in ds:
                raise ValueError("duplicate loop statements")
            ds["loop"] = ds.pop(k)
            ds["loop_with"] = loop_name

        return ds

    @classmethod
    def _validate_include_directives(cls, value: RawDirectives) -> RawDirectives:
        """Validate that include_* actions only include valid keywords."""
        action = cast(str, value["action"])
        if actions.is_include_tasks(action) or actions.is_include_role(action):
            diff = value.keys() - cls.VALID_INCLUDE_DIRECTIVES
            if diff:
                raise ValueError(
                    f"Unsupported directives for {value['action']} tasks: {', '.join(diff)}"
                )
        return value


class Task(BaseTask, frozen=True):
    """Represents an Ansible task."""


class Handler(BaseTask, frozen=True):
    """Represents an Ansible handler, a special type of task."""

    VALID_INCLUDE_DIRECTIVES: ClassVar[frozenset[str]] = (
        BaseTask.VALID_INCLUDE_DIRECTIVES | {"listen"}
    )

    #: Topics on which the handler listens
    listen: Annotated[Sequence[str], Listify] = Field(default_factory=tuple)


class Block(ASTNode, _CommonDirectives, frozen=True):
    """Represents an Ansible block of tasks."""

    # TODO: Verify whether handlers can occur in blocks and whether there should be a separate handler block.

    #: The block's main task list.
    block: Sequence[TaskOrBlock]
    #: List of tasks in the block's rescue section, i.e. the tasks that will
    #: execute when an exception occurs.
    rescue: Sequence[TaskOrBlock] = Field(default_factory=tuple)
    #: List of tasks in the block's always section, like a try-catch's `finally`
    #: handler.
    always: Sequence[TaskOrBlock] = Field(default_factory=tuple)

    #: List of handler names of handlers to notify.
    notify: Sequence[str] | None = None
    #: Delegate block execution to another host.
    delegate_to: str | None = None
    #: Apply facts to delegated host.
    delegate_facts: str | bool | None = None

    #: Condition on the block, or None if no condition.
    when: Annotated[Sequence[str | bool], Listify] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_task_lists(self) -> Self:
        """Validate that rescue and always are not used in empty blocks."""
        if (self.rescue or self.always) and not self.block:
            raise ValueError("`rescue` and `always` cannot be used in empty blocks")
        return self


def _distinguish_task_vs_block(obj: object) -> Literal["task", "block"] | None:
    if isinstance(obj, dict):
        if "block" in obj or "rescue" in obj or "always" in obj:
            return "block"
        return "task"
    if isinstance(obj, Task):
        return "task"
    if isinstance(obj, Block):
        return "block"

    raise ValueError("Expected block or task to be a dictionary")


type TaskOrBlock = Annotated[
    Annotated[Task, Tag("task")] | Annotated[Block, Tag("block")],
    Discriminator(_distinguish_task_vs_block),
]


class TaskFile(ASTFile, frozen=True):
    """Represents a file containing tasks and blocks."""

    #: The top-level tasks or blocks contained in the file, in the order of definition.
    tasks: Annotated[Sequence[TaskOrBlock], NormalizeNone, Lenient] = Field(
        default_factory=tuple
    )

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> TaskFile:
        return cls.model_validate(
            {"path": path.relative, "tasks": parse_file(path)}, context=context
        )


class HandlerFile(ASTFile, frozen=True):
    """Represents a file containing handlers."""

    #: The top-level handlers contained in the file, in the order of definition.
    handlers: Annotated[Sequence[Handler], NormalizeNone, Lenient] = Field(
        default_factory=tuple
    )

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> HandlerFile:
        return cls.model_validate(
            {"path": path.relative, "handlers": parse_file(path)}, context=context
        )


class SourceFileMap[FileType: ASTFile](Mapping[str, FileType]):
    """A collection of source files of a certain type, supporting stem-based indexing.

    This provides a convenient API to find source files without needing to take the concrete
    extension (.yml, .yaml, or .json) into account.

    Can optionally be given a search prefix. When provided, each lookup will attempt to resolve
    a prefixed file name, and fall back to unprefixed search later. This can be useful when all
    files in the map are in the same root directory. For instance, a file map for role task files
    can use "tasks/" as a prefix, allowing individual task files to be accessed without prefixing
    "tasks/" in the lookup.
    """

    def __init__(self, file_list: Iterable[FileType], *, prefix: str = "") -> None:
        self._mapping: Mapping[str, FileType] = FrozenDict(
            {str(file.path): file for file in file_list}
        )
        # If prefix is given, prioritise with the prefix but try without the prefix afterwards.
        self._prefixes: Sequence[str] = (prefix, "") if prefix else ("",)

    @override
    def __getitem__(self, key: str) -> FileType:
        for prefix in self._prefixes:
            for ext in (".yml", ".yaml", ".json", ""):
                file_name = f"{prefix}{key}{ext}"
                if file_name in self._mapping:
                    return self._mapping[file_name]

        raise KeyError(f"No file named {key}")

    @override
    def __len__(self) -> int:
        return len(self._mapping)

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)


type Extractor[T] = Callable[[ProjectPath, ExtractionContext], T]


def _safe_extract[T](
    extractor: Extractor[T], file_path: ProjectPath, ctx: ExtractionContext
) -> T | None:
    try:
        return extractor(file_path, ctx)
    except ValidationError as e:
        ctx.broken_files.append(BrokenFile(path=file_path.relative, reason=str(e)))


def _safe_extract_all[T](
    extractor: Extractor[T], file_paths: Sequence[ProjectPath], ctx: ExtractionContext
) -> Sequence[T]:
    results: list[T] = []
    for file_path in file_paths:
        if (result := _safe_extract(extractor, file_path, ctx)) is not None:
            results.append(result)
    return results


# Need arbitrary_types_allowed=True to put SourceFileMap into the model.
class Role(ASTFile, frozen=True, arbitrary_types_allowed=True):
    """Represents an Ansible role."""

    #: Role's main metadata file.
    meta_file: MetaFile | None
    #: Role's variable files in the defaults/* subdirectory, indexed by file name
    #: without directory prefix.
    default_var_files: SourceFileMap[VariableFile]
    #: Role's variable files in the vars/* subdirectory, indexed by file name
    #: without directory prefix.
    role_var_files: SourceFileMap[VariableFile]
    #: Role's task files in the tasks/* subdirectory, indexed by file name
    #: without directory prefix.
    task_files: SourceFileMap[TaskFile]
    #: Role's task files in the handlers/* subdirectory, indexed by file name
    #: without directory prefix.
    handler_files: SourceFileMap[HandlerFile]

    @cached_property
    def main_defaults_file(self) -> VariableFile | None:
        """The defaults/main.yml file."""
        return self.default_var_files.get("main")

    @cached_property
    def main_vars_file(self) -> VariableFile | None:
        """The vars/main.yml file."""
        return self.role_var_files.get("main")

    @cached_property
    def main_tasks_file(self) -> TaskFile | None:
        """The tasks/main.yml file."""
        return self.task_files.get("main")

    @cached_property
    def main_handlers_file(self) -> HandlerFile | None:
        """The handlers/main.yml file."""
        return self.handler_files.get("main")

    @classmethod
    @override
    def load(
        cls, path: ProjectPath, context: ExtractionContext, extract_all: bool = False
    ) -> Role:
        # Extract all constituents
        meta_file = None
        if (meta_file_path := find_file(path, "meta/main")) is not None:
            meta_file = _safe_extract(MetaFile.load, meta_file_path, context)

        if extract_all:
            gather_files = find_all_files
        else:

            def gather_files(dir_path: ProjectPath) -> Sequence[ProjectPath]:
                main_file = find_file(dir_path, "main")
                return [main_file] if main_file is not None else []

        task_files = _safe_extract_all(
            TaskFile.load, gather_files(path.join("tasks")), context
        )
        handler_files = _safe_extract_all(
            HandlerFile.load, gather_files(path.join("handlers")), context
        )
        vars_files = _safe_extract_all(
            VariableFile.load, gather_files(path.join("vars")), context
        )
        defaults_files = _safe_extract_all(
            VariableFile.load, gather_files(path.join("defaults")), context
        )

        return Role(
            path=path.relative,
            task_files=SourceFileMap(task_files, prefix="tasks/"),
            handler_files=SourceFileMap(handler_files, prefix="handlers/"),
            role_var_files=SourceFileMap(vars_files, prefix="vars/"),
            default_var_files=SourceFileMap(defaults_files, prefix="defaults/"),
            meta_file=meta_file,
        )


class VarsPrompt(ASTNode, frozen=True):
    """Represents a vars_prompt entry."""

    #: Name of the variable.
    name: Identifier
    #: Prompt to show.
    prompt: str | None = None
    #: Default value.
    default: AnyValue | None = None
    #: Whether to hide the input on the terminal (e.g. for passwords).
    private: str | bool | None = None
    #: Whether the user needs to re-enter to confirm.
    confirm: str | bool = False
    #: Encryption algorithm to use on the value.
    encrypt: str | None = None
    #: Salt size to use in encryption.
    salt_size: str | int | None = None
    #: Salt to use in encryption.
    salt: str | None = None
    #: Whether the user input is unsafe and should not be templated.
    unsafe: str | bool | None = None


class Play(ASTNode, _CommonDirectives, frozen=True):
    """Represents an Ansible play contained within a playbook."""

    #: The play's targetted hosts.
    hosts: Annotated[Sequence[str], Listify]
    #: The play's list of blocks.
    tasks: Sequence[TaskOrBlock] = Field(default_factory=tuple)

    #: Whether to gather facts from the remote hosts.
    gather_facts: bool | str | None = None

    #: Subset of facts to gather from remote hosts.
    gather_subset: Sequence[str] | None = None
    #: Timeout for fact gathering.
    gather_timeout: str | int | None = None
    #: Fact path option for fact gathering.
    fact_path: str | None = None

    #: List of files with variables to include into play.
    vars_files: Annotated[Sequence[Sequence[str]], NormalizeNone] = Field(
        default_factory=tuple
    )
    #: List of variables to prompt user for. List of mappings, `name` key
    #: contains variable name.
    vars_prompt: Sequence[VarsPrompt] = Field(default_factory=tuple)

    #: List of roles to be imported into play.
    roles: Sequence[PlayRoleRequirement] = Field(default_factory=tuple)

    #: Handlers for the play.
    handlers: Sequence[Handler] = Field(default_factory=tuple)
    #: Tasks to be run before the roles in `roles`.
    pre_tasks: Sequence[TaskOrBlock] = Field(default_factory=tuple)
    #: Tasks to be run after the main tasks.
    post_tasks: Sequence[TaskOrBlock] = Field(default_factory=tuple)

    #: Force handler notification.
    force_handlers: bool | str | None = None
    #: Maximum percentage of hosts that are allowed to fail before aborting play.
    max_fail_percentage: int | str | float | None = None
    #: Define how Ansible batches execution on hosts.
    serial: Sequence[str | int] = Field(default_factory=tuple)
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
        return new_value

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
        return cls.model_validate(
            {"path": path.relative, "plays": parse_file(path)}, context=context
        )


class AST(BaseModel, frozen=True):
    """Represents the AST root of a single role or playbook snapshot."""

    #: The path to the role or playbook. For roles, this points to a directory,
    #: for playbooks, this points to the playbook file.
    path: AbsolutePath
    #: The model root.
    root: Role | Playbook

    #: List of broken files that were omitted in lenient mode. Empty in strict mode.
    broken_files: Sequence[BrokenFile]
    #: List of broken tasks that were omitted in lenient mode. Empty in strict mode.
    broken_tasks: Sequence[BrokenTask]

    @property
    def is_role(self) -> bool:
        """Whether the model represents a role. Mutually exclusive with `is_playbook`."""
        return isinstance(self.root, Role)

    @property
    def is_playbook(self) -> bool:
        """Whether the model represents a playbook. Mutually exclusive with `is_role`."""
        return isinstance(self.root, Playbook)
