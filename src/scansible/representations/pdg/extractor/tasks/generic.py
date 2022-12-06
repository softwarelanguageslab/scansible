from __future__ import annotations

from collections.abc import Sequence

from loguru import logger

from ... import representation as rep
from ..result import ExtractionResult
from ..var_context import ScopeLevel
from .base import TaskExtractor

class GenericTaskExtractor(TaskExtractor):

    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:  # type: ignore[override]
        return frozenset({'name', 'action', 'args', 'vars', 'when', 'loop', 'loop_control', 'check_mode', 'register'})

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        logger.debug(f'Extracting task with name {self.task.name!r} from {self.location}')
        with self.context.vars.enter_cached_scope(ScopeLevel.TASK_VARS):
            for var_name, var_value in self.task.vars.items():
                self.context.vars.register_variable(var_name, expr=var_value, level=ScopeLevel.TASK_VARS)

            if self.task.loop:
                result = self._extract_looping_task(predecessors)
            else:
                result = self._extract_single_task(predecessors)

            self.warn_remaining_kws('generic tasks')
            return result

    def _extract_single_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        if self.task.loop_control:
            self.context.graph.errors.append('Found loop_control without loop')

        tn, cn = self._extract_bare_task(predecessors)
        registered_var = self._define_registered_var([tn])
        added: list[rep.ControlNode] = [tn]
        # Condition could be false, so the task could be skipped and the
        # condition itself could also be a predecessor.
        if cn is not None:
            added.append(cn)

        return ExtractionResult(
            next_predecessors=added,
            added_variable_nodes=[] if registered_var is None else [registered_var],
            added_control_nodes=added)

    def _extract_looping_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        loop_node = rep.Loop(location=self.context.get_location(self.task.loop) or self.location)
        source_and_name = self.extract_looping_value_and_name()
        assert source_and_name is not None, 'Internal error'

        loop_source_var, loop_var_name = source_and_name
        self.context.graph.add_node(loop_node)
        self.context.graph.add_edge(loop_source_var, loop_node, rep.USE)
        for pred in predecessors:
            self.context.graph.add_edge(pred, loop_node, rep.ORDER)

        # For some reason, loop vars have the same precedence as include params.
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.register_variable(loop_var_name, ScopeLevel.INCLUDE_PARAMS)
            self.context.graph.add_edge(loop_source_var, loop_target_var, rep.DEF_LOOP_ITEM)

            tn, cn = self._extract_bare_task([loop_node])
            # Back edge to represent looping. Forward edge already added by the
            # called method.
            self.context.graph.add_edge(tn, loop_node, rep.ORDER_BACK)
            # If there was a conditional node added by the task, its "else" branch
            # needs to link back to the loop. If a loop step is skipped, the next
            # task will be the next step in the loop.
            if cn is not None:
                self.context.graph.add_edge(cn, loop_node, rep.ORDER_BACK)

        # It could be that the source list is empty, in which case the task will
        # be skipped and there will be a direct edge from the loop to the next
        # task. If it isn't skipped, it'll always have to go back to the loop
        # too
        result = ExtractionResult([loop_node, tn], [], [loop_node])
        # Any registered variable is defined both by the loop and the individual tasks
        if (registered_var := self._define_registered_var([loop_node, tn])) is not None:
            result = result.add_variable_nodes(registered_var)
        if cn is not None:
            result = result.add_control_nodes(cn)

        return result

    def _extract_bare_task(self, predecessors: Sequence[rep.ControlNode]) -> tuple[rep.Task, rep.Conditional | None]:
        tn = rep.Task(name=self.task.name, action=self.task.action, location=self.location)
        cn: rep.Conditional | None = None
        first_node: rep.ControlNode = tn
        self.context.graph.add_node(tn)

        if (condition_val_node := self.extract_conditional_value()) is not None:
            # Add a conditional node, which uses the expression IV, and is
            # succeeded by the task itself.
            cn = rep.Conditional(location=self.context.get_location(self.task.when) or self.location)
            self.context.graph.add_node(cn)
            self.context.graph.add_edge(condition_val_node, cn, rep.USE)
            self.context.graph.add_edge(cn, tn, rep.ORDER)
            first_node = cn

        for pred in predecessors:
            self.context.graph.add_edge(pred, first_node, rep.ORDER)

        # Link data flow
        for arg_name, arg_value in self.task.args.items():
            arg_node = self.extract_value(arg_value)
            self.context.graph.add_edge(arg_node, tn, rep.Keyword(keyword=f'args.{arg_name}'))

        misc_kws = {'check_mode',}
        for misc_kw in misc_kws:
            if not self.task.is_default(misc_kw, (kw_val := getattr(self.task, misc_kw))):
                val_node = self.extract_value(kw_val)
                self.context.graph.add_edge(val_node, tn, rep.Keyword(keyword=misc_kw))

        return tn, cn

    def _define_registered_var(self, definers: list[rep.ControlNode]) -> rep.Variable | None:
        if (registered_var_name := self.task.register):
            assert isinstance(registered_var_name, str)
            vn = self.context.vars.register_variable(registered_var_name, ScopeLevel.SET_FACTS_REGISTERED)
            self.context.graph.add_node(vn)
            # There could be multiple defining control nodes, e.g. the loop node and the task node.
            for definer in definers:
                self.context.graph.add_edge(definer, vn, rep.DEF)
            return vn
        return None
