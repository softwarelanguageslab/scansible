"""AST node representations."""

# pyright: reportUnknownVariableType = false

# FIXME!!! Source code position information is largely broken due to Pydantic coercing Ansible types (AnsibleUnicode, AnsibleMapping, ...)
# to plain data types (str, dict, ...), losing the custom `ansible_pos` field.

from __future__ import annotations

from typing import Annotated, Self, cast, get_args, get_origin, override

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping, Sequence
from functools import cached_property
from pathlib import Path

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    PositiveInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.fields import FieldInfo

from scansible.representations.structural.helpers import ProjectPath, parse_file
from scansible.types import AnyValue, ScalarValue
from scansible.utils import FrozenDict


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


#: Relative paths in the project
type RelativePath = Annotated[Path, AfterValidator(_validate_relative_path)]

#: Absolute paths in the project
type AbsolutePath = Annotated[Path, AfterValidator(_validate_absolute_path)]


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
    def _get_contained_type(cls, field_info: FieldInfo) -> type[ASTEntity]:
        annotation = field_info.annotation

        if (
            annotation is None
            or (origin := get_origin(annotation)) is None
            or not issubclass(origin, Sequence)
        ):
            raise ValueError("Can only mark Sequences as Lenient")

        (contained_type,) = get_args(annotation)  # pyright: ignore[reportAny]
        if not issubclass(contained_type, ASTEntity):
            raise ValueError("Can only leniently parse AST entities")

        return contained_type

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if not isinstance(value, Sequence):
            return value

        if not isinstance(validation_info.context, ExtractionContext):
            raise ValueError("Expected context to be an ExtractionContext")

        context = validation_info.context
        if not context.lenient:
            return value

        contained_type = cls._get_contained_type(field_info)

        results: list[ASTEntity] = []
        for raw in value:
            try:
                results.append(
                    contained_type.model_validate(raw, context=validation_info.context)
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
    def load(cls: type[Self], file: ProjectPath, context: ExtractionContext) -> Self:
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
    def load(cls, file: ProjectPath, context: ExtractionContext) -> BrokenFile:
        raise NotImplementedError("Cannot load a broken file.")


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
    vars: Mapping[str, AnyValue] = Field(default_factory=FrozenDict)

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
    def load(cls, file: ProjectPath, context: ExtractionContext) -> MetaFile:
        return cls.model_validate(
            {"path": file.relative, "metablock": parse_file(file)}, context=context
        )


class VariableFile(ASTFile, frozen=True):
    """Represents a file containing variables."""

    #: The variables contained within the file. The order is irrelevant.
    variables: Annotated[Mapping[str, AnyValue], NormalizeNone] = Field(
        default_factory=dict
    )

    @classmethod
    @override
    def load(cls, file: ProjectPath, context: ExtractionContext) -> VariableFile:
        return cls.model_validate(
            {"path": file.relative, "variables": parse_file(file)}, context=context
        )


class LoopControl(ASTNode, frozen=True):
    """Represents the loop control directive value."""

    #: The loop variable name. `item` by default.
    loop_var: str = "item"
    #: The index variable name.
    index_var: str | None = None
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

    #: Action of the task.
    action: str
    #: Arguments to the action.
    args: Mapping[str, AnyValue]

    #: Run task asynchronously for at most the given number of seconds.
    async_val: str | int | None = 0
    #: Conditional expression(s) to override "changed" status.
    changed_when: Sequence[str | bool] = Field(default_factory=tuple)
    #: Number of seconds to delay between retries.
    delay: str | float | int | None = 5.0
    #: Delegate task execution to another host.
    delegate_to: str | None = None
    #: Apply facts to delegated host.
    delegate_facts: str | bool | None = None
    #: Conditional expression(s) to override the "failed" status.
    failed_when: Sequence[str | bool] = Field(default_factory=tuple)
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
    #: the result of this action.
    register: str | None = None
    #: Number of tries for failed tasks.
    retries: str | int | None = None
    #: Retry task until condition(s) are satisfied.
    until: Sequence[str | bool] = Field(default_factory=tuple)
    #: Condition on the task, or None if no condition.
    when: Sequence[str | bool] = Field(default_factory=tuple)


class Task(BaseTask, frozen=True):
    """Represents an Ansible task."""


class Handler(BaseTask, frozen=True):
    """Represents an Ansible handler, a special type of task."""

    #: Topics on which the handler listens
    listen: Sequence[str] = Field(default_factory=tuple)


class Block(ASTNode, _CommonDirectives, frozen=True):
    """Represents an Ansible block of tasks."""

    # TODO: Verify whether handlers can occur in blocks and whether there should be a separate handler block.

    #: The block's main task list.
    block: Sequence[Task | Block]
    #: List of tasks in the block's rescue section, i.e. the tasks that will
    #: execute when an exception occurs.
    rescue: Sequence[Task | Block] = Field(default_factory=tuple)
    #: List of tasks in the block's always section, like a try-catch's `finally`
    #: handler.
    always: Sequence[Task | Block] = Field(default_factory=tuple)

    #: List of handler names of handlers to notify.
    notify: Sequence[str] | None = None
    #: Delegate block execution to another host.
    delegate_to: str | None = None
    #: Apply facts to delegated host.
    delegate_facts: str | bool | None = None

    #: Condition on the block, or None if no condition.
    when: Sequence[str | bool] = Field(default_factory=tuple)


class TaskFile(ASTFile, frozen=True):
    """Represents a file containing tasks and blocks."""

    #: The top-level tasks or blocks contained in the file, in the order of definition.
    tasks: Sequence[Block | Task]

    @classmethod
    @override
    def load(cls, file: ProjectPath, context: ExtractionContext) -> TaskFile:
        return cls.model_validate(
            {"path": file.relative, "tasks": parse_file(file)}, context=context
        )


class HandlerFile(ASTFile, frozen=True):
    """Represents a file containing handlers."""

    #: The top-level handlers contained in the file, in the order of definition.
    handlers: Sequence[Handler]

    @classmethod
    @override
    def load(cls, file: ProjectPath, context: ExtractionContext) -> HandlerFile:
        return cls.model_validate(
            {"path": file.relative, "handlers": parse_file(file)}, context=context
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
    #: Role's list of broken files.
    broken_files: Sequence[BrokenFile]
    #: Role's list of broken tasks.
    broken_tasks: Sequence[BrokenTask]

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
    def load(cls, file: ProjectPath, context: ExtractionContext) -> Role:
        # FIXME: Copy-pasted but need to populate fields
        return cls.model_validate({"path": file.relative}, context=context)


class VarsPrompt(ASTNode, frozen=True):
    """Represents a vars_prompt entry."""

    #: Name of the variable.
    name: str
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
    hosts: Sequence[str]
    #: The play's list of blocks.
    tasks: Sequence[Task | Block] = Field(default_factory=tuple)

    #: Whether to gather facts from the remote hosts.
    gather_facts: bool | str | None = None

    #: Subset of facts to gather from remote hosts.
    gather_subset: Sequence[str] | None = None
    #: Timeout for fact gathering.
    gather_timeout: str | int | None = None
    #: Fact path option for fact gathering.
    fact_path: str | None = None

    #: List of files with variables to include into play.
    vars_files: Sequence[str | Sequence[str]] = Field(default_factory=tuple)
    #: List of variables to prompt user for. List of mappings, `name` key
    #: contains variable name.
    vars_prompt: Sequence[VarsPrompt] = Field(default_factory=tuple)

    #: List of roles to be imported into play.
    roles: Sequence[PlayRoleRequirement] = Field(default_factory=tuple)

    #: Handlers for the play.
    handlers: Sequence[Handler] = Field(default_factory=tuple)
    #: Tasks to be run before the roles in `roles`.
    pre_tasks: Sequence[Task | Block] = Field(default_factory=tuple)
    #: Tasks to be run after the main tasks.
    post_tasks: Sequence[Task | Block] = Field(default_factory=tuple)

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


class Playbook(ASTFile, frozen=True):
    """Represents an Ansible playbook."""

    #: List of plays defined in this playbook.
    plays: Sequence[Play]
    #: Playbook's list of broken tasks.
    broken_tasks: Sequence[BrokenTask] = Field(default_factory=tuple)
    #: Playbook's list of broken files. Currently always empty.
    broken_files: Sequence[BrokenFile] = Field(default_factory=tuple)

    @classmethod
    @override
    def load(cls, file: ProjectPath, context: ExtractionContext) -> Playbook:
        # FIXME: Copy-pasted but need to populate broken_tasks and broken_files
        return cls.model_validate(
            {"path": file.relative, "plays": parse_file(file)}, context=context
        )


class AST(BaseModel, frozen=True):
    """Represents the AST root of a single role or playbook snapshot."""

    #: The path to the role or playbook. For roles, this points to a directory,
    #: for playbooks, this points to the playbook file.
    path: AbsolutePath
    #: The model root.
    root: Role | Playbook

    @property
    def is_role(self) -> bool:
        """Whether the model represents a role. Mutually exclusive with `is_playbook`."""
        return isinstance(self.root, Role)

    @property
    def is_playbook(self) -> bool:
        """Whether the model represents a playbook. Mutually exclusive with `is_role`."""
        return isinstance(self.root, Playbook)
