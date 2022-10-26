"""Structural model for roles."""
from __future__ import annotations

from typing import (
        Any,
        Dict,
        List,
        Union,
        TypeVar,
)

from pathlib import Path

from attrs import define, frozen, field
from ansible.parsing.yaml.objects import AnsibleSequence, AnsibleMapping, AnsibleUnicode


# Type aliases
VariableContainer = Union['VariableFile', 'Task', 'Block', 'Play']
TaskContainer = Union['Block', 'Play', 'TaskFile']
Scalar = Union[bool, int, float, AnsibleUnicode]
AnyValue = Union[Scalar, AnsibleSequence, AnsibleMapping]


@frozen
class BrokenFile:
    """
    Represents a file that could not be parsed.
    """

    #: The path to the file.
    path: Path
    #: The reason why the file is broken.
    reason: str


@frozen
class Platform:
    """
    Represents a platform supported by a role.
    """

    #: Platform name.
    name: str
    #: Platform version.
    version: str


@frozen
class Dependency:
    """
    Represents a role dependency.
    """

    # TODO!


@define
class MetaFile:
    """
    Represents a file containing role metadata.
    """

    #: The path to the file, relative to the project root.
    file_path: Path
    #: The metadata block contained in the file.
    metablock: MetaBlock


@define
class MetaBlock:
    """
    Represents a role metadata block.
    """

    #: The parent file of this metadata block.
    parent: MetaFile = field(init=False, repr=False)
    #: Platforms supported by the role
    platforms: list[Platform]
    #: Role dependencies
    dependencies: list[Dependency]

    #: Raw information present in the metadata block, some which may not
    #: explicitly be parsed.
    raw: Any = field(repr=False)


@define
class Variable:
    """
    Represents a variable.
    """

    #: Variable name.
    name: str
    #: Variable value.
    value: AnyValue
    #: Parent wherein the variable is defined. Either a file containing variables
    #: (in defaults/ or vars/), a task, a block, or a play.
    parent: VariableContainer = field(init=False, repr=False)


@define
class VariableFile:
    """
    Represents a file containing variables.
    """

    #: The path to the file, relative to the project root.
    file_path: Path
    #: The variables contained within the file. The order is irrelevant.
    variables: list[Variable]  # TODO: Use a set


@define(slots=False)
class TaskBase:
    """
    Represents a basic Ansible task.
    """

    #: Parent block in which the task is contained.
    parent: TaskContainer = field(init=False, repr=False)
    #: Name of the task.
    name: str | None
    #: Action of the task.
    action: str
    #: Arguments to the action.
    args: dict[str, AnyValue]
    #: Condition on the task, or None if no condition.
    when: list[str]
    #: Loop on the task, or None if no loop.
    loop: str | list[str] | None
    #: Loop control defined on the task.
    loop_control: Any  # TODO!
    #: Variables defined on the task
    vars: list[Variable]  # TODO: Should be a set, since order doesn't matter

    #: Raw information present in the task, some which may not explicitly be parsed.
    raw: Any = field(repr=False)


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
    listen: list[str]


@define
class Block:
    """
    Represents an Ansible block of tasks.
    """

    # TODO: This doesn't support handlers. Can handlers be placed in a block?

    #: Parent block or file wherein this block is contained as a child.
    parent: TaskContainer = field(init=False, repr=False)
    #: Name of the block
    name: str | None

    #: The block's main task list.
    block: list[Task | Block]
    #: List of tasks in the block's rescue section, i.e. the tasks that will
    #: execute when an exception occurs.
    rescue: list[Task | Block]
    #: List of tasks in the block's always section, like a try-catch's `finally`
    #: handler.
    always: list[Task | Block]
    #: Set of variables defined on this block.
    vars: list[Variable]  # TODO: Should be a set

    #: Raw information present in the block, some which may not explicitly be parsed.
    raw: Any = field(repr=False)


@define
class TaskFile:
    """
    Represents a file containing tasks and blocks.
    """

    #: The path to the file, relative to the project root.
    file_path: Path
    #: The top-level tasks or blocks contained in the file, in the order of
    #: definition. Can also be a list of handlers, but handlers and task/blocks
    #: cannot be mixed.
    tasks: list[Block | Task] | list[Handler]


@define
class Role:
    """
    Represents an Ansible role.
    """

    #: Role's main metadata file.
    meta_file: MetaFile | None
    #: Role's variable files in the defaults/* subdirectory, indexed by file name
    #: without directory prefix.
    default_var_files: dict[str, VariableFile]
    #: Role's variable files in the vars/* subdirectory, indexed by file name
    #: without directory prefix.
    role_var_files: dict[str, VariableFile]
    #: Role's task files in the tasks/* subdirectory, indexed by file name
    #: without directory prefix.
    task_files: dict[str, TaskFile]
    #: Role's task files in the handlers/* subdirectory, indexed by file name
    #: without directory prefix.
    handler_files: dict[str, TaskFile]
    #: Role's list of broken files.
    broken_files: list[BrokenFile]
    #: Output from Ansible that was caught while parsing.
    logs: list[str]

    #: The defaults/main file.
    main_defaults_file: VariableFile | None = field(init=False)
    #: The vars/main file.
    main_vars_file: VariableFile | None = field(init=False)
    #: The tasks/main file.
    main_tasks_file: TaskFile | None = field(init=False)
    #: The handlers/main file.
    main_handlers_file: TaskFile | None = field(init=False)

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
    parent: Playbook = field(init=False, repr=False)

    #: The play's name.
    name: str
    #: The play's targetted hosts.
    hosts: list[str]
    #: The play's list of blocks.
    tasks: list[Task | Block]
    #: The play-level variables.
    vars: list[Variable]  # TODO: Should be a set

    # TODO: Handlers, pre- and post-tasks, roles, vars files, vars_prompt, etc?

    #: Raw information present in the play, some which may not explicitly be parsed.
    raw: Any = field(repr=False)


@define
class Playbook:
    """
    Represents an Ansible playbook.
    """

    #: List of plays defined in this playbook.
    plays: list[Play]
    #: Output from Ansible that was caught
    logs: list[str]

    #: Raw information present in the playbook, some which may not explicitly be parsed.
    raw: Any = field(repr=False)


@define
class StructuralModel:
    """
    Represents a structural model of a single role or playbook version.
    """

    #: The model root.
    root: Role | Playbook
    #: The path to the role or playbook. For roles, this points to a directory,
    #: for playbooks, this points to the playbook file.
    path: Path
    #: A user-defined ID for the role or playbook.
    id: str
    #: A user-defined version for the role or playbook (often a git tag or commit SHA).
    version: str
    #: Whether the model represents a role. Mutually exclusive with `is_playbook`.
    is_role: bool = field(init=False)
    #: Whether the model represents a playbook. Mutually exclusive with `is_role`.
    is_playbook: bool = field(init=False)

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
    id: str
    #: Map of versions to structural models.
    structural_models: dict[str, StructuralModel]
