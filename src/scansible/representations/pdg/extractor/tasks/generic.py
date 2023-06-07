from __future__ import annotations

from collections.abc import Sequence

from ... import representation as rep
from ..expressions import EnvironmentType, RecursiveDefinitionError
from ..result import ExtractionResult
from .base import TaskExtractor


class GenericTaskExtractor(TaskExtractor):
    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:
        return (
            super()
            .SUPPORTED_TASK_ATTRIBUTES()
            .union(
                {
                    "vars",
                    "loop",
                    "loop_control",
                    "check_mode",
                    "register",
                    "become",
                    "become_user",
                    "become_method",
                    "notify",
                }
            )
        )

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        self.logger.debug(f"Extracting task with name {self.task.name!r}")
        with self.setup_task_vars_scope(EnvironmentType.TASK_VARS):
            if self.task.loop:
                result = self._extract_looping_task(predecessors)
            else:
                result = self._extract_single_task(predecessors)

            self.warn_remaining_kws("generic tasks")
            return result

    def _extract_single_task(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        if self.task.loop_control:
            self.logger.warning("Found loop_control without loop")

        return self._extract_bare_task(predecessors)

    def _extract_looping_task(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        source_and_name = self.extract_looping_info()
        assert source_and_name is not None, "Internal error"

        loop_source_var, loop_var_name, loop_with = source_and_name

        # For some reason, loop vars have the same precedence as include params.
        with self.context.vars.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.define_injected_variable(
                loop_var_name, EnvironmentType.INCLUDE_PARAMS
            )
            self.context.graph.add_edge(
                loop_source_var, loop_target_var, rep.DefLoopItem(loop_with)
            )

            with self.context.activate_loop(loop_source_var):
                inner_result = self._extract_bare_task(predecessors)
            # Add a loop edge to indicate single-task loop.
            assert len(inner_result.added_control_nodes) == 1
            self.context.graph.add_edge(
                inner_result.added_control_nodes[0],
                inner_result.added_control_nodes[0],
                rep.ORDER_BACK,
            )

        return inner_result

    def _extract_bare_task(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        tn = rep.Task(
            name=self.task.name, action=self.task.action, location=self.location
        )
        self.context.graph.add_node(tn)

        for pred in predecessors:
            self.context.graph.add_edge(pred, tn, rep.ORDER)

        # Link conditions
        condition_nodes = self.extract_conditions()
        with self.context.activate_conditions(condition_nodes):
            for condition_node in self.context.active_conditions:
                self.context.graph.add_edge(condition_node, tn, rep.WHEN)

        # Link loops
        for loop_node in self.context.active_loops:
            self.context.graph.add_edge(loop_node, tn, rep.LOOP)

        # Link data flow
        for arg_name, arg_value in self.task.args.items():
            try:
                arg_node = self.context.vars.build_expression(arg_value)
            except RecursiveDefinitionError as e:
                self.logger.error(e)
                continue
            self.context.graph.add_edge(
                arg_node, tn, rep.Keyword(keyword=f"args.{arg_name}")
            )

        # Definition of the registered var doesn't depend on the condition of this
        # task, so do it when the conditions have already been deactivated.
        self._define_registered_var(tn)

        for notified_handler in self.task.notify or []:
            self.context.handler_notifications[notified_handler].add(tn)

        misc_kws = {"check_mode", "become", "become_user", "become_method"}
        for misc_kw in misc_kws:
            if not self.task.is_default(
                misc_kw, (kw_val := getattr(self.task, misc_kw))
            ):
                try:
                    val_node = self.context.vars.build_expression(kw_val)
                except RecursiveDefinitionError as e:
                    self.logger.error(e)
                    continue
                self.context.graph.add_edge(val_node, tn, rep.Keyword(keyword=misc_kw))

        result = ExtractionResult.single(tn)
        # If the task is executed conditionally, the next predecessor may also
        # be any of the previous ones if the task was skipped.
        if condition_nodes:
            result = result.add_next_predecessors(predecessors)
        return result

    def _define_registered_var(self, task: rep.Task) -> None:
        if not self.task.register:
            return

        vn = self.context.vars.define_injected_variable(
            self.task.register, EnvironmentType.SET_FACTS_REGISTERED
        )
        self.context.graph.add_edge(task, vn, rep.DEF)
        for condition in self.context.active_conditions:
            self.context.graph.add_edge(condition, vn, rep.WHEN)
