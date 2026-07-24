# pyright: reportUnknownVariableType = false

"""AST nodes for tasks, blocks, and handlers.

These nodes include the parsing and normalization of task directives
from Ansible's various shorthand and obsoleted syntaxes.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal, Self, cast, override

from collections.abc import Mapping

from ansible.parsing.splitter import parse_kv, split_args
from ansible.utils.fqcn import add_internal_fqcns
from pydantic import Discriminator, Field, Tag, field_validator, model_validator

from scansible.representations.cst import parse_file
from scansible.types import AnyValue, ScalarValue
from scansible.utils import ProjectPath, actions

from ..common import ExtractionContext, RawDirectives
from .base import ASTFile, ASTNode
from .directives import CommonDirectives
from .expression import (
    AnyExpression,
    BoolLiteral,
    Condition,
    Expression,
    FloatLiteral,
    Identifier,
    IntLiteral,
    LenientSeqLiteral,
    MapLiteral,
    ScalarLiteral,
    SeqLiteral,
    StrLiteral,
)

# Adapted from ansible.constants
#: Unqualified names of actions that take freeform (unparsed) arguments.
FREEFORM_ACTIONS_SIMPLE = (
    "command",
    "raw",
    "script",
    "shell",
    "win_command",
    "win_shell",
)
#: `FREEFORM_ACTIONS_SIMPLE`, expanded with their fully-qualified collection names.
FREEFORM_ACTIONS = frozenset(
    tuple(add_internal_fqcns(FREEFORM_ACTIONS_SIMPLE))
    + ("ansible.windows.win_command", "ansible.windows.win_shell")
)


class LoopControl(ASTNode, frozen=True):
    """Represents the loop control directive value."""

    #: The loop variable name. `item` by default.
    loop_var: Identifier = Identifier("item")
    #: The index variable name.
    index_var: Identifier | None = None
    #: Loop label in output.
    label: StrLiteral | None = None
    #: Amount of time in seconds to pause between each iteration.
    pause: FloatLiteral | Expression = FloatLiteral(0.0)
    #: Whether to include more information in the loop items.
    #: See https://docs.ansible.com/ansible/latest/user_guide/playbooks_loops.html#extended-loop-variables
    extended: BoolLiteral | Expression | None = None
    #: Whether to include `allitems` in the extended version.
    extended_allitems: BoolLiteral | Expression | None = BoolLiteral(True)
    #: Conditions when to break the loop.
    break_when: SeqLiteral[Condition | BoolLiteral] = Field(default_factory=SeqLiteral)


class BaseTask(ASTNode, CommonDirectives, frozen=True):
    """Represents commonalities for Ansible tasks."""

    #: Directives permitted on `include_tasks`/`import_tasks`/`include_role` tasks.
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
    action: StrLiteral
    #: Arguments to the action.
    args: MapLiteral[StrLiteral, AnyExpression]

    #: Run task asynchronously for at most the given number of seconds.
    async_val: IntLiteral | Expression | None = Field(
        default=IntLiteral(0), alias="async"
    )
    #: Conditional expression(s) to override "changed" status.
    changed_when: SeqLiteral[Condition | BoolLiteral] = Field(
        default_factory=SeqLiteral
    )
    #: Number of seconds to delay between retries.
    delay: FloatLiteral | Expression | None = FloatLiteral(5.0)
    #: Delegate task execution to another host.
    delegate_to: StrLiteral | None = None
    #: Apply facts to delegated host.
    delegate_facts: BoolLiteral | Expression | None = None
    #: Conditional expression(s) to override the "failed" status.
    failed_when: SeqLiteral[Condition | BoolLiteral] = Field(default_factory=SeqLiteral)
    #: Loop on the task, or None if no loop. Can be an expression, a list of
    #: arbitrary values, or, when the loop comes from `with_dict`, a dict of
    #: arbitrary items.
    loop: (
        Expression
        | SeqLiteral[AnyExpression]
        | MapLiteral[ScalarLiteral, AnyExpression]
        | None
    ) = None
    #: The type of loop used in old looping syntax (`with_*`), e.g.
    #: `with_items` -> `items`.
    loop_with: StrLiteral | None = None
    #: Loop control defined on the task.
    loop_control: LoopControl | None = None
    #: List of handler names of handlers to notify.
    notify: SeqLiteral[StrLiteral] = Field(default_factory=SeqLiteral)
    #: Polling interval for async tasks.
    poll: IntLiteral | Expression | None = None
    #: Value given to the register keyword, i.e. variable name that will store
    #: the result of this action. Renamed due to naming conflicts with base classes.
    register_var: Identifier | None = Field(default=None, alias="register")
    #: Number of tries for failed tasks.
    retries: IntLiteral | Expression | None = None
    #: Retry task until condition(s) are satisfied.
    until: SeqLiteral[Condition | BoolLiteral] = Field(default_factory=SeqLiteral)
    #: Conditions on the task.
    when: SeqLiteral[Condition | BoolLiteral] = Field(default_factory=SeqLiteral)

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
        action, action_args = cls._flatten_old_style_action_and_arguments(
            ds.pop("action")
        )
        arg_list.extend(action_args)

        # action could be "xyz" or "xyz a=b c=d", split it.
        [action, *freeform_args] = split_args(action)
        arg_list.append(" ".join(freeform_args))

        ds["action"] = action
        ds["args"] = cls._combine_args(action, *arg_list)

        return ds

    @classmethod
    def _flatten_old_style_action_and_arguments(
        cls, action: AnyValue
    ) -> tuple[str, list[AnyValue]]:
        """Given an old-style action specification, extract the action and separate the arguments."""
        arg_list: list[AnyValue] = []
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

        return action, arg_list

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
        """Parse a raw `key=value` argument string, treating `action` specially if it's a freeform action."""
        check_raw = action in FREEFORM_ACTIONS
        return parse_kv(args, check_raw)  # pyright: ignore[reportReturnType]

    @classmethod
    def _parse_task_level_args(
        cls, ds: RawDirectives
    ) -> Mapping[ScalarValue, AnyValue]:
        """Pop and normalize the task-level `args` directive."""
        task_args = ds.pop("args", {})
        if isinstance(task_args, str):
            task_args = {"_variable_params": task_args}
        return task_args  # pyright: ignore[reportReturnType]

    @classmethod
    def _combine_args(cls, action: str, *arg_list: AnyValue) -> AnyValue:
        """Merge multiple argument sources into one dict, lowest to highest priority."""
        combined_args = {}
        for args in arg_list:
            if isinstance(args, str):
                args = cls._parse_args(action, args)
            if args == None:  # noqa: E711 -- could be YamlNone
                args = {}
            if not isinstance(args, dict):
                raise ValueError("Expected args to be a dictionary")
            combined_args.update(args)  # pyright: ignore[reportUnknownMemberType]

        return combined_args

    @classmethod
    def _all_directives(cls) -> set[str]:
        """Return the set of directives that exist on this entity."""
        return {field.alias or name for name, field in cls.model_fields.items()}

    @classmethod
    def _is_task_directive(cls, key: str) -> bool:
        """Whether `key` is a recognized task directive rather than a module action."""
        return (
            key in cls._all_directives() or key == "static" or key.startswith("with_")
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
        """Translate legacy `with_*` loop directives into `loop`/`loop_with`."""
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

    #: Directives permitted on `include_tasks`/`import_tasks`/`include_role` handlers.
    VALID_INCLUDE_DIRECTIVES: ClassVar[frozenset[str]] = (
        BaseTask.VALID_INCLUDE_DIRECTIVES | {"listen"}
    )

    #: Topics on which the handler listens.
    listen: SeqLiteral[StrLiteral] = Field(default_factory=SeqLiteral)


class Block(ASTNode, CommonDirectives, frozen=True):
    """Represents an Ansible block of tasks."""

    # TODO: Verify whether handlers can occur in blocks and whether there should be a separate handler block.

    #: The block's main task list.
    block: SeqLiteral[TaskOrBlock]
    #: List of tasks in the block's rescue section, i.e. the tasks that will
    #: execute when an exception occurs.
    rescue: SeqLiteral[TaskOrBlock] = Field(default_factory=SeqLiteral)
    #: List of tasks in the block's always section, like a try-catch's `finally`
    #: handler.
    always: SeqLiteral[TaskOrBlock] = Field(default_factory=SeqLiteral)

    #: List of handler names of handlers to notify.
    notify: SeqLiteral[StrLiteral] = Field(default_factory=SeqLiteral)
    #: Delegate block execution to another host.
    delegate_to: StrLiteral | None = None
    #: Apply facts to delegated host.
    delegate_facts: BoolLiteral | Expression | None = None

    #: Conditions on the block.
    when: SeqLiteral[Condition | BoolLiteral] = Field(default_factory=SeqLiteral)

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


#: A task-list entry: either a `Task` or a `Block`, discriminated by whether
#: the raw data contains `block`/`rescue`/`always` keys.
type TaskOrBlock = Annotated[
    Annotated[Task, Tag("task")] | Annotated[Block, Tag("block")],
    Discriminator(_distinguish_task_vs_block),
]


class TaskFile(ASTFile, frozen=True):
    """Represents a file containing tasks and blocks."""

    #: The top-level tasks or blocks contained in the file, in the order of definition.
    tasks: LenientSeqLiteral[TaskOrBlock] = Field(default_factory=LenientSeqLiteral)

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> TaskFile:
        """Load and parse a tasks file from the given path."""
        return cls.model_validate(
            {"path": path.relative, "tasks": parse_file(path)}, context=context
        )


class HandlerFile(ASTFile, frozen=True):
    """Represents a file containing handlers."""

    #: The top-level handlers contained in the file, in the order of definition.
    handlers: LenientSeqLiteral[Handler] = Field(default_factory=LenientSeqLiteral)

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> HandlerFile:
        """Load and parse a handlers file from the given path."""
        return cls.model_validate(
            {"path": path.relative, "handlers": parse_file(path)}, context=context
        )


__all__ = [
    "LoopControl",
    "BaseTask",
    "Task",
    "Handler",
    "Block",
    "TaskFile",
    "HandlerFile",
    "TaskOrBlock",
]
