from __future__ import annotations

from typing import Literal

import abc
from collections.abc import Generator, Sequence
from contextlib import contextmanager

from scansible.representations.structural import TaskBase

from ... import representation as rep
from ..context import ExtractionContext
from ..result import ExtractionResult

class TaskExtractor(abc.ABC):

    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:
        return frozenset({'name', 'action', 'args', 'when', 'vars'})

    def __init__(self, context: ExtractionContext, task: TaskBase) -> None:
        self.context = context
        self.task = task
        self.location = context.get_location(task)

    @abc.abstractmethod
    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        raise NotImplementedError('To be implemented by subclass')

    def extract_conditional_value(self) -> rep.DataNode | None:
        if not self.task.when:
            return None

        if not isinstance(self.task.when, list):
            self.context.graph.errors.append(f'Cannot handle {type(self.task.when)} conditionals!')
        elif len(self.task.when) > 1:
            self.context.graph.errors.append(f'Cannot handle multiple conditions yet!')
        else:
            return self.extract_value(self.task.when[0], is_conditional=True)

        return None

    def extract_looping_value_and_name(self) -> tuple[rep.DataNode, str] | None:
        loop_expr = self.task.loop
        if not loop_expr:
            return None

        loop_source_var = self.extract_value(loop_expr)

        if self.task.loop_with:
            self.context.graph.errors.append(f'I cannot handle looping style {self.task.loop_with!r} yet!')

        if self.task.loop_control:
            loop_var_name = self.task.loop_control.loop_var or 'item'

            for loop_control_k, _ in self.task.loop_control._get_non_default_attributes():
                if loop_control_k == 'loop_var':
                    continue
                self.context.graph.errors.append(f'I cannot handle loop_control option {loop_control_k} yet!')
        else:
            loop_var_name = 'item'

        return loop_source_var, loop_var_name

    # TODO: This doesn't really belong here...
    def extract_value(self, value: object, is_conditional: bool = False) -> rep.DataNode:
        if isinstance(value, str):
            tr = self.context.vars.evaluate_template(value, is_conditional)
            return tr.data_node
        else:
            return self.context.vars.add_literal(value)

    @contextmanager
    def setup_task_vars_scope(self, scope_level: Literal[ScopeLevel.TASK_VARS, ScopeLevel.INCLUDE_PARAMS]) -> Generator[None, None, None]:
        # TODO: Revisit this when we re-introduce caching, sometimes the scope may be cached.
        with self.context.vars.enter_scope(scope_level):
            VariablesExtractor(self.context, self.task.vars).extract_variables(scope_level)
            yield

    def warn_remaining_kws(self, action: str = '') -> None:
        for other_kw, _ in self.task._get_non_default_attributes():
            if not other_kw in self.SUPPORTED_TASK_ATTRIBUTES() and other_kw != 'raw':
                self.context.graph.errors.append(f'Cannot handle {other_kw} on {action or self.task.action} yet!')
