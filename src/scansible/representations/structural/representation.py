"""Structural model for roles."""
from __future__ import annotations

from typing import (
        Any,
        Callable,
        Dict,
        List,
        Mapping,
        Union,
        TypeVar,
)

import types
from pathlib import Path

import attrs
from attrs import define, frozen, field
from attrs_strict import AttributeTypeError, type_validator as old_type_validator
from ansible.parsing.yaml.objects import AnsibleSequence, AnsibleMapping, AnsibleUnicode


# Type aliases
VariableContainer = Union['VariableFile', 'Task', 'Block', 'Play']
TaskContainer = Union['Block', 'Play', 'TaskFile']
Scalar = Union[bool, int, float, str]
# These should be recursive types, but mypy doesn't support them so they'd be
# Any anyway, and it also doesn't work with our type validation.
AnyValue = Union[Scalar, list[Any], dict[Scalar, Any]]

def _convert_union_type(type_: Any) -> object:
    if isinstance(type_, types.UnionType):
        return Union.__getitem__(tuple(_convert_union_type(arg) for arg in type_.__args__))

    if not isinstance(type_, types.GenericAlias):
        return type_

    if type_.__origin__ in (list, dict):
        return types.GenericAlias(type_.__origin__, tuple(_convert_union_type(arg) for arg in type_.__args__))
    return type_


# Patch for https://github.com/bloomberg/attrs-strict/issues/80
def type_validator(empty_ok: bool = True) -> Callable[[Any, attrs.Attribute[Any], Any], None]:
    old_validator = old_type_validator(empty_ok)

    # Convert types.UnionType into typing.Union recursively.
    def convert_types(attribute: attrs.Attribute[Any]) -> None:
        # Use object.__setattr__ to workaround frozen attr.Attribute
        object.__setattr__(attribute, 'type', _convert_union_type(attribute.type))

    def converting_validator(instance: Any, attribute: attrs.Attribute[Any], field: Any) -> None:
        try:
            convert_types(attribute)
            old_validator(instance, attribute, field)
        except AttributeTypeError as e:
            # from __future__ import annotations leads to the original type
            # annotation being a string, so it's possible that we couldn't
            # convert the union type earlier because we got a string instead
            # of types.UnionType. By now, attrs-strict should've resolved those
            # types, so try again.
            if not e.__context__ or e.__context__.__class__.__name__ != '_StringAnnotationError':
                raise
            convert_types(attribute)
            old_validator(instance, attribute, field)

    return converting_validator


def default_field() -> Any:
    return field(validator=type_validator())


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


@frozen
class BrokenFile:
    """
    Represents a file that could not be parsed.
    """

    #: The path to the file.
    path: Path = field(validator=validate_relative_path)
    #: The reason why the file is broken.
    reason: str = default_field()


@frozen
class Platform:
    """
    Represents a platform supported by a role.
    """

    #: Platform name.
    name: str = default_field()
    #: Platform version.
    version: str | int | float = default_field()


@frozen
class Dependency:
    """
    Represents a role dependency.
    """

    #: The role that is depended upon.
    role: str = default_field()
    #: Optional condition on when to include a dependency.
    when: list[str] = default_field()


@define
class MetaFile:
    """
    Represents a file containing role metadata.
    """

    #: The path to the file, relative to the project root.
    file_path: Path = field(validator=validate_relative_path)
    #: The metadata block contained in the file.
    metablock: MetaBlock = default_field()


@define
class MetaBlock:
    """
    Represents a role metadata block.
    """

    #: Raw information present in the metadata block, some which may not
    #: explicitly be parsed.
    raw: Any = field(repr=False)

    #: The parent file of this metadata block.
    parent: MetaFile = field(init=False, repr=False, eq=False, validator=type_validator())
    #: Platforms supported by the role
    platforms: list[Platform] = default_field()
    #: Role dependencies
    dependencies: list[Dependency] = default_field()


@define
class Variable:
    """
    Represents a variable.
    """

    #: Variable name.
    name: str = default_field()
    #: Variable value.
    value: AnyValue | None = default_field()
    #: Parent wherein the variable is defined. Either a file containing variables
    #: (in defaults/ or vars/), a task, a block, or a play.
    parent: VariableContainer = field(init=False, repr=False, eq=False, validator=type_validator())


@define
class VariableFile:
    """
    Represents a file containing variables.
    """

    #: The path to the file, relative to the project root.
    file_path: Path = field(validator=validate_relative_path)
    #: The variables contained within the file. The order is irrelevant.
    variables: list[Variable] = default_field() # TODO: Use a set


@define
class LoopControl:
    """
    Represents the loop control directive value.
    """

    #: The loop variable name. `item` by default.
    loop_var: str = default_field()
    #: The index variable name.
    index_var: str | None = default_field()
    #: Loop label in output.
    label: str | None = default_field()
    #: Amount of time in seconds to pause between each iteration. Can be a
    #: string in case this is an expression. 0 by default.
    pause: str | int | float = default_field()
    #: Whether to include more information in the loop items.
    #: See https://docs.ansible.com/ansible/latest/user_guide/playbooks_loops.html#extended-loop-variables
    extended: str | bool | None = default_field()


@define(slots=False)
class TaskBase:
    """
    Represents a basic Ansible task.
    """

    #: Raw information present in the task, some which may not explicitly be parsed.
    raw: Any = field(repr=False)
    #: Parent block in which the task is contained.
    parent: TaskContainer = field(init=False, repr=False, eq=False, validator=type_validator())
    #: Name of the task.
    name: str | None = default_field()
    #: Action of the task.
    action: str = default_field()
    #: Arguments to the action.
    args: Mapping[str, AnyValue] = default_field()
    #: Condition on the task, or None if no condition.
    when: list[str | bool] = default_field()
    #: Loop on the task, or None if no loop. Can be a string (an expression),
    #: a list of arbitrary values, or, when the loop comes from `with_dict`, a
    #: dict of arbitrary items.
    loop: str | list[AnyValue] | dict[Scalar, AnyValue] | None = default_field()
    #: The type of loop used in old looping syntax (`with_*`), e.g.
    #: `with_items` -> `items`.
    loop_with: str | None = default_field()
    #: Loop control defined on the task.
    loop_control: LoopControl | None = default_field()
    #: Value given to the register keyword, i.e. variable name that will store
    #: the result of this action.
    register: str | None = default_field()
    #: Variables defined on the task
    vars: list[Variable] = default_field()  # TODO: Should be a set, since order doesn't matter


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
    listen: list[str] = default_field()


@define
class Block:
    """
    Represents an Ansible block of tasks.
    """

    #: Raw information present in the block, some which may not explicitly be parsed.
    raw: Any = field(repr=False)
    #: Parent block or file wherein this block is contained as a child.
    parent: TaskContainer = field(init=False, repr=False, eq=False, validator=type_validator())
    #: Name of the block
    name: str | None = default_field()

    #: The block's main task list.
    block: list[Task | Block] | list[Handler | Block] = default_field()
    #: List of tasks in the block's rescue section, i.e. the tasks that will
    #: execute when an exception occurs.
    rescue: list[Task | Block] | list[Handler | Block] = default_field()
    #: List of tasks in the block's always section, like a try-catch's `finally`
    #: handler.
    always: list[Task | Block] | list[Handler | Block] = default_field()
    #: Set of variables defined on this block.
    vars: list[Variable] = default_field()  # TODO: Should be a set


@define
class TaskFile:
    """
    Represents a file containing tasks and blocks.
    """

    #: The path to the file, relative to the project root.
    file_path: Path = field(validator=validate_relative_path)
    #: The top-level tasks or blocks contained in the file, in the order of
    #: definition. Can also be a list of handlers (or blocks thereof), but
    #: handlers and tasks cannot be mixed.
    tasks: list[Block | Task] | list[Block | Handler] = default_field()


@define
class Role:
    """
    Represents an Ansible role.
    """

    #: Role's main metadata file.
    meta_file: MetaFile | None = default_field()
    #: Role's variable files in the defaults/* subdirectory, indexed by file name
    #: without directory prefix.
    default_var_files: dict[str, VariableFile] = default_field()
    #: Role's variable files in the vars/* subdirectory, indexed by file name
    #: without directory prefix.
    role_var_files: dict[str, VariableFile] = default_field()
    #: Role's task files in the tasks/* subdirectory, indexed by file name
    #: without directory prefix.
    task_files: dict[str, TaskFile] = default_field()
    #: Role's task files in the handlers/* subdirectory, indexed by file name
    #: without directory prefix.
    handler_files: dict[str, TaskFile] = default_field()
    #: Role's list of broken files.
    broken_files: list[BrokenFile] = default_field()

    #: The defaults/main file.
    main_defaults_file: VariableFile | None = field(init=False, validator=type_validator())
    #: The vars/main file.
    main_vars_file: VariableFile | None = field(init=False, validator=type_validator())
    #: The tasks/main file.
    main_tasks_file: TaskFile | None = field(init=False, validator=type_validator())
    #: The handlers/main file.
    main_handlers_file: TaskFile | None = field(init=False, validator=type_validator())

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
class Play:
    """
    Represents an Ansible play contained within a playbook.
    """

    #: The playbook in which this play is contained.
    parent: Playbook = field(init=False, repr=False, eq=False, validator=type_validator())
    #: Raw information present in the play, some which may not explicitly be parsed.
    raw: Any = field(repr=False)
    #: The play's name.
    name: str = default_field()
    #: The play's targetted hosts.
    hosts: list[str] = default_field()
    #: The play's list of blocks.
    tasks: list[Task | Block] = default_field()
    #: The play-level variables.
    vars: list[Variable] = default_field()  # TODO: Should be a set

    # TODO: Handlers, pre- and post-tasks, roles, vars files, vars_prompt, etc?


@define
class Playbook:
    """
    Represents an Ansible playbook.
    """

    #: Raw information present in the playbook, some which may not explicitly be parsed.
    raw: Any = field(repr=False)
    #: List of plays defined in this playbook.
    plays: list[Play] = default_field()


@define
class StructuralModel:
    """
    Represents a structural model of a single role or playbook version.
    """

    #: The path to the role or playbook. For roles, this points to a directory,
    #: for playbooks, this points to the playbook file.
    path: Path = field(validator=validate_absolute_path)
    #: The model root.
    root: Role | Playbook = default_field()
    #: A user-defined ID for the role or playbook.
    id: str = default_field()
    #: A user-defined version for the role or playbook (often a git tag or commit SHA).
    version: str = default_field()
    #: Output from Ansible that was caught
    logs: str = default_field()
    #: Whether the model represents a role. Mutually exclusive with `is_playbook`.
    is_role: bool = field(init=False, validator=type_validator())
    #: Whether the model represents a playbook. Mutually exclusive with `is_role`.
    is_playbook: bool = field(init=False, validator=type_validator())

    def __attrs_post_init__(self) -> None:
        self.is_role = isinstance(self.root, Role)
        self.is_playbook = isinstance(self.root, Playbook)
        assert self.is_role != self.is_playbook, 'is_role and is_playbook should be mutually exclusive, and one should be set.'


@define
class MultiStructuralModel:
    """
    Represents the structural model of multiple versions of a role or playbook.
    """

    #: A user-defined ID for the role or playbook.
    id: str = default_field()
    #: Map of versions to structural models.
    structural_models: dict[str, StructuralModel] = default_field()
