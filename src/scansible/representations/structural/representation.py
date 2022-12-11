"""Structural model for roles."""
from __future__ import annotations

from typing import (
        Any,
        Callable,
        Generic,
        Iterable,
        Mapping,
        Protocol,
        Sequence,
        TypeVar,
        Union,
        cast,
)

import datetime
import re
import types
from abc import abstractmethod
from functools import reduce
from itertools import chain
from pathlib import Path

import attrs
import rich.repr
from attrs import define, frozen, field
from ansible.parsing.yaml.objects import AnsibleSequence, AnsibleMapping, AnsibleUnicode

from . import ansible_types as ans
from .._utils import type_validator


# Type aliases
TaskContainer = Union['Block', 'Play', 'TaskFile']
Scalar = Union[bool, int, float, str, 'VaultValue', datetime.date, datetime.datetime, None]
# These should be recursive types, but mypy doesn't support them so they'd be
# Any anyway, and it also doesn't work with our type validation.
AnyValue = Union[Scalar, Sequence[Any], Mapping[Scalar, Any]]
Position = tuple[str, int, int]


def default_field(default: Any = attrs.NOTHING, factory: Any = None) -> Any:
    if default is attrs.NOTHING and factory is None:
        raise TypeError('Either a default value or a factory needs to be specified')
    return field(validator=type_validator(), default=default, factory=factory)

def raise_if_missing() -> None:
    raise ValueError('Missing required field')

def required_field() -> Any:
    # necessary because otherwise we can't do inheritance with defaults in super
    # and required params in sub.
    return default_field(factory=raise_if_missing)

def parent_field() -> Any:
    return field(init=False, repr=False, eq=False, validator=type_validator())

def raw_field() -> Any:
    return field(repr=False, eq=False)

def position_field() -> Any:
    return field(repr=False, eq=False, default=('unknown file', -1, -1))

def path_field() -> Any:
    return field(validator=validate_relative_path)


def validate_relative_path(inst: Any, attr: attrs.Attribute[Path], value: Path) -> None:
    if not isinstance(value, Path):
        raise TypeError(f'Expected {attr.name} to be a Path, got {value} of type {type(value)} instead')
    if value.is_absolute():
        raise ValueError(f'Expected {attr.name} to be a relative path, got absolute path {value} instead')


def validate_absolute_path(inst: Any, attr: attrs.Attribute[Path], value: Path) -> None:
    if not isinstance(value, Path):
        raise TypeError(f'Expected {attr.name} to be a Path, got {value} of type {type(value)} instead')
    if not value.is_absolute():
        raise ValueError(f'Expected {attr.name} to be an absolute path, got relative path {value} instead')


VisitorReturnType = TypeVar('VisitorReturnType', covariant=True)


class StructuralVisitor(Protocol[VisitorReturnType]):
    @abstractmethod
    def visit_block(self, v: Block) -> VisitorReturnType: ...
    @abstractmethod
    def visit_broken_file(self, v: BrokenFile) -> VisitorReturnType: ...
    @abstractmethod
    def visit_broken_task(self, v: BrokenTask) -> VisitorReturnType: ...
    @abstractmethod
    def visit_handler(self, v: Handler) -> VisitorReturnType: ...
    @abstractmethod
    def visit_loop_control(self, v: LoopControl) -> VisitorReturnType: ...
    @abstractmethod
    def visit_meta_block(self, v: MetaBlock) -> VisitorReturnType: ...
    @abstractmethod
    def visit_meta_file(self, v: MetaFile) -> VisitorReturnType: ...
    @abstractmethod
    def visit_multi_structural_model(self, v: MultiStructuralModel) -> VisitorReturnType: ...
    @abstractmethod
    def visit_platform(self, v: Platform) -> VisitorReturnType: ...
    @abstractmethod
    def visit_play(self, v: Play) -> VisitorReturnType: ...
    @abstractmethod
    def visit_playbook(self, v: Playbook) -> VisitorReturnType: ...
    @abstractmethod
    def visit_role(self, v: Role) -> VisitorReturnType: ...
    @abstractmethod
    def visit_role_requirement(self, v: RoleRequirement) -> VisitorReturnType: ...
    @abstractmethod
    def visit_role_source_info(self, v: RoleSourceInfo) -> VisitorReturnType: ...
    @abstractmethod
    def visit_structural_model(self, v: StructuralModel) -> VisitorReturnType: ...
    @abstractmethod
    def visit_task(self, v: Task) -> VisitorReturnType: ...
    @abstractmethod
    def visit_task_file(self, v: TaskFile) -> VisitorReturnType: ...
    @abstractmethod
    def visit_variable_file(self, v: VariableFile) -> VisitorReturnType: ...
    @abstractmethod
    def visit_vars_prompt(self, v: VarsPrompt) -> VisitorReturnType: ...


class StructuralBase:

    def accept(self, visitor: StructuralVisitor[VisitorReturnType]) -> VisitorReturnType:
        cls_name_snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', self.__class__.__name__).lower()
        method_name = f'visit_{cls_name_snake_case}'
        return getattr(visitor, method_name)(self)  # type: ignore[no-any-return]

    @classmethod
    def is_default(cls, attr_name: str, attr_value: Any) -> bool:  # type: ignore[misc]
        attr = next(a for a in cls.__attrs_attrs__ if a.name == attr_name)  # type: ignore[attr-defined]
        default = attr.default
        return not (
            # If there's no default specified...
            default is attrs.NOTHING
            or (default is not None and isinstance(default, attrs.Factory) and (  # type: ignore[arg-type]
                # or if it's a factory but it raises if no value is specified
                default.factory is raise_if_missing
                # or if it's a factory and the factory value is different from the actual value
                or default.factory() != attr_value))
            # or if it's a value and it's different from the actual value.
            or (not isinstance(default, attrs.Factory) and attr_value != default))  # type: ignore[arg-type]

    def _yield_non_default_representable_attributes(self) -> Iterable[tuple[str, Any]]:
        for attr in self.__attrs_attrs__:  # type: ignore[attr-defined]
            if not attr.repr:
                continue

            name = attr.name
            value = getattr(self, name)

            if self.is_default(name, value):
                yield name, value

    def _get_non_default_attributes(self) -> list[tuple[str, Any]]:
        return [
            (name, value)
            for attr in self.__attrs_attrs__  # type: ignore[attr-defined]
            if not self.is_default((name := attr.name), (value := getattr(self, name)))]

    __rich_repr__ = _yield_non_default_representable_attributes


@frozen(str=False)
class VaultValue(StructuralBase):
    """
    Represents an Ansible encrypted vault value.
    """

    #: The encrypted data.
    data: bytes
    #: Position of the value.
    location: Position = position_field()

    def __str__(self) -> str:
        return self.data.decode()


@frozen
class BrokenTask(StructuralBase):
    """
    Represents a task/block that could not be extracted.
    """

    #: The raw datastructure that failed to extract.
    ds: Any = required_field()
    #: The reason for failure.
    reason: str = required_field()


@frozen
class BrokenFile(StructuralBase):
    """
    Represents a file that could not be parsed or extracted.
    """

    #: The path to the file.
    path: Path = path_field()
    #: The reason why the file is broken.
    reason: str = required_field()


@frozen
class Platform(StructuralBase):
    """
    Represents a platform supported by a role.
    """

    #: Platform name.
    name: str = required_field()
    #: Platform version.
    version: str = required_field()
    #: Position of the value.
    location: Position = position_field()


@define
class MetaFile(StructuralBase):
    """
    Represents a file containing role metadata.
    """

    #: The path to the file, relative to the project root.
    file_path: Path = path_field()
    #: The metadata block contained in the file.
    metablock: MetaBlock = required_field()


@define
class MetaBlock(StructuralBase):
    """
    Represents a role metadata block.
    """

    #: Raw information present in the metadata block, some which may not
    #: explicitly be parsed.
    raw: Any = raw_field()
    #: Position of the value.
    location: Position = position_field()

    #: The parent file of this metadata block.
    parent: MetaFile = parent_field()
    #: Platforms supported by the role
    platforms: Sequence[Platform] = default_field(factory=list)
    #: Role dependencies
    dependencies: Sequence['RoleRequirement'] = default_field(factory=list)


@define
class VariableFile(StructuralBase):
    """
    Represents a file containing variables.
    """

    #: Raw content of the variable file.
    raw: Any = raw_field()
    #: The path to the file, relative to the project root.
    file_path: Path = path_field()
    #: The variables contained within the file. The order is irrelevant.
    variables: Mapping[str, AnyValue] = required_field()


@define
class LoopControl(StructuralBase):
    """
    Represents the loop control directive value.
    """

    #: Position of the value.
    location: Position = position_field()
    #: The loop variable name. `item` by default.
    loop_var: str = default_field(default='item')
    #: The index variable name.
    index_var: str | None = default_field(default=None)
    #: Loop label in output. Should technically be a string only, but Ansible
    #: doesn't complain about dicts and just templates and stringifies those.
    label: AnyValue = default_field(default=None)
    #: Amount of time in seconds to pause between each iteration. Can be a
    #: string in case this is an expression. 0 by default.
    pause: str | int | float = default_field(default=0)
    #: Whether to include more information in the loop items.
    #: See https://docs.ansible.com/ansible/latest/user_guide/playbooks_loops.html#extended-loop-variables
    extended: str | bool | None = default_field(default=None)


@define(slots=False)
class DirectivesBase(StructuralBase):
    """
    Represents the common Ansible directives.
    """

    #: Raw information present in the entity.
    raw: Any = raw_field()
    #: Position of the value.
    location: Position = position_field()

    #: Name of the task.
    name: str | None = default_field(default='')

    #: Change the connection plugin.
    connection: str | None = default_field(default=None)
    #: Override default port in connection.
    port: int | None = default_field(default=None)
    #: Remote user name.
    remote_user: str | None = default_field(default=None)

    #: Variables defined on the entity.
    vars: Mapping[str, AnyValue] = default_field(factory=dict)

    #: Specify default arguments to modules in this entity.
    module_defaults: list[Mapping[str, Mapping[str, AnyValue]]] | None = default_field(default=None)

    #: Dictionary converted into environment variables.
    environment: Sequence[Mapping[str, str] | str] | None = default_field(default=None)
    #: To disable logging of action.
    no_log: bool | str | None = default_field(default=None)
    #: Run on a single host only.
    run_once: bool | str | None = default_field(default=None)
    #: Ignore task failures.
    ignore_errors: bool | str | None = default_field(default=None)
    #: Ignore task failures due to unreachable host.
    ignore_unreachable: bool | str | None = default_field(default=None)
    #: Toggle check mode (dry run).
    check_mode: bool | str | None = default_field(default=None)
    #: Toggle returning diff information from task.
    diff: bool | str | None = default_field(default=None)
    #: End play once one task fails for one host.
    any_errors_fatal: bool | str | None = default_field(default=ans.C.ANY_ERRORS_FATAL)
    #: Max amount of hosts to operate on in parallel.
    throttle: str | int | None = default_field(default=0)
    #: Task timeout.
    timeout: str | int | None = default_field(default=ans.C.TASK_TIMEOUT)

    #: Set debugger state.
    debugger: str | None = default_field(default=None)

    #: Whether to perform privilege escalation.
    become: str | bool | None = default_field(default=None)
    #: How to perform privilege escalation (sudo, su, ...)
    become_method: str | None = default_field(default=None)
    #: User to escalate to.
    become_user: str | None = default_field(default=None)
    #: Flags to pass to privilege escalation program.
    become_flags: str | None = default_field(default=None)
    #: Path to privilege escalation executable.
    become_exe: str | None = default_field(default=None)


@define(slots=False)
class TaskBase(DirectivesBase):
    """
    Represents a basic Ansible task.
    """

    #: Parent block in which the task is contained.
    parent: TaskContainer = parent_field()

    #: Action of the task.
    action: str = required_field()
    #: Arguments to the action.
    args: Mapping[str, AnyValue] = required_field()

    #: Run task asynchronously for at most the given number of seconds.
    async_val: str | int | None = default_field(default=0)
    #: Conditional expression(s) to override "changed" status.
    changed_when: Sequence[str | bool] = default_field(factory=list)
    #: Number of seconds to delay between retries.
    delay: str | int | None = default_field(default=5)
    #: Delegate task execution to another host.
    delegate_to: str | None = default_field(default=None)
    #: Apply facts to delegated host.
    delegate_facts: str | bool | None = default_field(default=None)
    #: Conditional expression(s) to override the "failed" status.
    failed_when: Sequence[str | bool] = default_field(factory=list)
    #: Loop on the task, or None if no loop. Can be a string (an expression),
    #: a list of arbitrary values, or, when the loop comes from `with_dict`, a
    #: dict of arbitrary items.
    loop: str | Sequence[AnyValue] | Mapping[Scalar, AnyValue] | None = default_field(default=None)
    #: The type of loop used in old looping syntax (`with_*`), e.g.
    #: `with_items` -> `items`.
    loop_with: str | None = default_field(default=None)
    #: Loop control defined on the task.
    loop_control: LoopControl | None = default_field(default=None)
    #: List of handler names of handlers to notify.
    notify: Sequence[str] | None = default_field(default=None)
    #: Polling interval for async tasks.
    poll: str | int | None = default_field(default=ans.C.DEFAULT_POLL_INTERVAL)
    #: Value given to the register keyword, i.e. variable name that will store
    #: the result of this action.
    register: str | None = default_field(default=None)
    #: Number of tries for failed tasks.
    retries: str | int | None = default_field(default=3)
    #: Retry task until condition(s) are satisfied.
    until: Sequence[str | bool] = default_field(factory=list)
    #: Condition on the task, or None if no condition.
    when: Sequence[str | bool] = default_field(factory=list)
    #: Tags on the task.
    tags: Sequence[str | int] = default_field(factory=list)
    #: List of collections to search for modules.
    collections: Sequence[str] = default_field(factory=list)


@define(slots=False)
class Task(TaskBase):
    """
    Represents an Ansible task.
    """


@define(slots=False)
class Handler(TaskBase):
    """
    Represents an Ansible handler, a special type of task.
    """

    #: Topics on which the handler listens
    listen: Sequence[str] = default_field(factory=list)


@define
class Block(DirectivesBase):
    """
    Represents an Ansible block of tasks.
    """

    #: Parent block or file wherein this block is contained as a child.
    parent: TaskContainer = parent_field()

    #: The block's main task list.
    block: Sequence[Task | Block] | Sequence[Handler | Block] = required_field()
    #: List of tasks in the block's rescue section, i.e. the tasks that will
    #: execute when an exception occurs.
    rescue: Sequence[Task | Block] | Sequence[Handler | Block] = default_field(factory=list)
    #: List of tasks in the block's always section, like a try-catch's `finally`
    #: handler.
    always: Sequence[Task | Block] | Sequence[Handler | Block] = default_field(factory=list)

    #: List of handler names of handlers to notify.
    notify: Sequence[str] | None = default_field(default=None)
    #: Delegate block execution to another host.
    delegate_to: str | None = default_field(default=None)
    #: Apply facts to delegated host.
    delegate_facts: str | bool | None = default_field(default=None)

    #: Condition on the block, or None if no condition.
    when: Sequence[str | bool] = default_field(factory=list)
    #: Tags on the block.
    tags: Sequence[str | int] = default_field(factory=list)
    #: List of collections to search for modules.
    collections: Sequence[str] = default_field(factory=list)


@frozen
class RoleSourceInfo(StructuralBase):
    """
    Represents source info for a role requirement.
    """

    #: Name of the role.
    name: str | None
    #: Source URL.
    src: str | None
    #: Source control management system (git, hg, ...).
    scm: str | None
    #: Role version.
    version: str | None


@define(slots=False)
class RoleRequirement(DirectivesBase):
    """
    Represents a role inclusion dependency in a play's `roles` directive or
    a role's `dependencies` (old-style only).
    """

    #: Position of the value.
    location: Position = position_field()
    #: The role that is depended upon.
    role: str = required_field()

    #: The role include parameters.
    params: Mapping[str, AnyValue] = default_field(factory=dict)

    #: Delegate execution to another host.
    delegate_to: str | None = default_field(default=None)
    #: Apply facts to delegated host. Contrary to tasks, the default here is False.
    delegate_facts: str | bool | None = default_field(default=False)

    #: Tags on the role inclusion.
    tags: Sequence[str | int] = default_field(factory=list)
    #: List of collections to search for modules.
    collections: Sequence[str] = default_field(factory=list)
    #: Optional condition on when to include a dependency.
    when: Sequence[str | bool] = default_field(factory=list)

    #: Source info for role. Possibly available for role requirements coming
    #: from a role's meta/main.yml metadata file, but never for plays.
    source_info: RoleSourceInfo | None = default_field(default=None)


@define
class TaskFile(StructuralBase):
    """
    Represents a file containing tasks and blocks.
    """

    #: The path to the file, relative to the project root.
    file_path: Path = path_field()
    #: The top-level tasks or blocks contained in the file, in the order of
    #: definition. Can also be a list of handlers (or blocks thereof), but
    #: handlers and tasks cannot be mixed.
    tasks: Sequence[Block | Task] | Sequence[Block | Handler] = required_field()


@define
class Role(StructuralBase):
    """
    Represents an Ansible role.
    """

    #: Role's main metadata file.
    meta_file: MetaFile | None = required_field()
    #: Role's variable files in the defaults/* subdirectory, indexed by file name
    #: without directory prefix.
    default_var_files: dict[str, VariableFile] = required_field()
    #: Role's variable files in the vars/* subdirectory, indexed by file name
    #: without directory prefix.
    role_var_files: dict[str, VariableFile] = required_field()
    #: Role's task files in the tasks/* subdirectory, indexed by file name
    #: without directory prefix.
    task_files: dict[str, TaskFile] = required_field()
    #: Role's task files in the handlers/* subdirectory, indexed by file name
    #: without directory prefix.
    handler_files: dict[str, TaskFile] = required_field()
    #: Role's list of broken files.
    broken_files: list[BrokenFile] = required_field()
    #: Role's list of broken tasks.
    broken_tasks: list[BrokenTask] = required_field()

    #: The defaults/main file.
    main_defaults_file: VariableFile | None = field(init=False, validator=type_validator(), repr=False)
    #: The vars/main file.
    main_vars_file: VariableFile | None = field(init=False, validator=type_validator(), repr=False)
    #: The tasks/main file.
    main_tasks_file: TaskFile | None = field(init=False, validator=type_validator(), repr=False)
    #: The handlers/main file.
    main_handlers_file: TaskFile | None = field(init=False, validator=type_validator(), repr=False)

    def __attrs_post_init__(self) -> None:

        # TODO: We need to lookup files in the graph builder too, so perhaps
        # we should create a custom subtype of dict and provide that.
        FileType = TypeVar('FileType')
        def find_file(file_map: dict[str, FileType], stem: str) -> FileType | None:
            for ext in ('.yml', '.yaml', '.json'):
                file_name = f'{stem}{ext}'
                if file_name in file_map:
                    return file_map[file_name]
            return None

        self.main_defaults_file = find_file(self.default_var_files, 'main')
        self.main_vars_file = find_file(self.role_var_files, 'main')
        self.main_tasks_file = find_file(self.task_files, 'main')
        self.main_handlers_file = find_file(self.handler_files, 'main')


@define
class VarsPrompt(StructuralBase):
    """Represents a vars_prompt entry."""

    #: Position of the value.
    location: Position = position_field()
    #: Name of the variable.
    name: str = required_field()
    #: Prompt to show.
    prompt: str = default_field(default=None)
    #: Default value.
    default: AnyValue = default_field(default=None)
    #: Whether to hide the input on the terminal (e.g. for passwords).
    private: str | bool | None = default_field(default=True)
    #: Whether the user needs to re-enter to confirm.
    confirm: str | bool = default_field(default=False)
    #: Encryption algorithm to use on the value.
    encrypt: str | None = default_field(default=None)
    #: Salt size to use in encryption.
    salt_size: str | int | None = default_field(default=None)
    #: Salt to use in encryption.
    salt: str | None = default_field(default=None)
    #: Whether the user input is unsafe and should not be templated.
    unsafe: str | bool | None = default_field(default=None)


@define
class Play(DirectivesBase):
    """
    Represents an Ansible play contained within a playbook.
    """

    #: Position of the value.
    location: Position = position_field()
    #: The playbook in which this play is contained.
    parent: Playbook = parent_field()
    #: The play's targetted hosts.
    hosts: Sequence[str] = required_field()
    #: The play's list of blocks.
    tasks: Sequence[Task | Block] = default_field(factory=list)

    #: Whether to gather facts from the remote hosts.
    gather_facts: bool | str | None = default_field(default=None)

    #: Subset of facts to gather from remote hosts.
    gather_subset: Sequence[str] | None = default_field(default=None)
    #: Timeout for fact gathering.
    gather_timeout: str | int | None = default_field(default=None)
    #: Fact path option for fact gathering.
    fact_path: str | None = default_field(default=None)

    #: List of files with variables to include into play.
    vars_files: Sequence[str | Sequence[str]] = default_field(factory=list)
    #: List of variables to prompt user for. List of mappings, `name` key
    #: contains variable name.
    vars_prompt: Sequence[VarsPrompt] = default_field(factory=list)

    #: List of roles to be imported into play.
    roles: Sequence[RoleRequirement] = default_field(factory=list)

    #: Handlers for the play.
    handlers: Sequence[Handler | Block] = default_field(factory=list)
    #: Tasks to be run before the roles in `roles`.
    pre_tasks: Sequence[Task | Block] = default_field(factory=list)
    #: Tasks to be run after the main tasks.
    post_tasks: Sequence[Task | Block] = default_field(factory=list)

    #: Force handler notification.
    force_handlers: bool | str | None = default_field(default=None)
    #: Maximum percentage of hosts that are allowed to fail before aborting play.
    max_fail_percentage: int | str | float | None = default_field(default=None)
    #: Define how Ansible batches execution on hosts.
    serial: Sequence[str | int] = default_field(factory=list)
    #: Execution strategy related to parallel host execution.
    strategy: str | None = default_field(default=ans.C.DEFAULT_STRATEGY)
    #: How hosts should be sorted in execution order.
    order: str | None = default_field(default=None)

    #: Tags on the play.
    tags: Sequence[str | int] = default_field(factory=list)
    #: List of collections to search for modules.
    collections: Sequence[str] = default_field(factory=list)


@define
class Playbook(StructuralBase):
    """
    Represents an Ansible playbook.
    """

    #: Raw information present in the playbook, some which may not explicitly be parsed.
    raw: Any = raw_field()
    #: List of plays defined in this playbook.
    plays: Sequence[Play] = required_field()
    #: Playbook's list of broken tasks.
    broken_tasks: list[BrokenTask] = required_field()
    #: Playbook's list of broken files. Currently always empty.
    broken_files: list[BrokenFile] = default_field(factory=list)


@define
class StructuralModel(StructuralBase):
    """
    Represents a structural model of a single role or playbook version.
    """

    #: The path to the role or playbook. For roles, this points to a directory,
    #: for playbooks, this points to the playbook file.
    path: Path = field(validator=validate_absolute_path)
    #: The model root.
    root: Role | Playbook = required_field()
    #: A user-defined ID for the role or playbook.
    id: str = required_field()
    #: A user-defined version for the role or playbook (often a git tag or commit SHA).
    version: str = required_field()
    #: Output from Ansible that was caught
    logs: str = required_field()
    #: Whether the model represents a role. Mutually exclusive with `is_playbook`.
    is_role: bool = field(init=False, validator=type_validator())
    #: Whether the model represents a playbook. Mutually exclusive with `is_role`.
    is_playbook: bool = field(init=False, validator=type_validator())

    def __attrs_post_init__(self) -> None:
        self.is_role = isinstance(self.root, Role)
        self.is_playbook = isinstance(self.root, Playbook)
        assert self.is_role != self.is_playbook, 'is_role and is_playbook should be mutually exclusive, and one should be set.'


@define
class MultiStructuralModel(StructuralBase):
    """
    Represents the structural model of multiple versions of a role or playbook.
    """

    #: A user-defined ID for the role or playbook.
    id: str = required_field()
    #: Map of versions to structural models.
    structural_models: dict[str, StructuralModel] = required_field()
