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
        loop_node = rep.Loop(
            loop_with=loop_with,
            location=self.context.get_location(self.task.loop) or self.location,
        )
        self.context.graph.add_node(loop_node)
        self.context.graph.add_edge(loop_source_var, loop_node, rep.USE)
        for pred in predecessors:
            self.context.graph.add_edge(pred, loop_node, rep.ORDER)

        # For some reason, loop vars have the same precedence as include params.
        with self.context.vars.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.define_injected_variable(
                loop_var_name, EnvironmentType.INCLUDE_PARAMS
            )
            self.context.graph.add_edge(
                loop_source_var, loop_target_var, rep.DEF_LOOP_ITEM
            )

            inner_result = self._extract_bare_task([loop_node])
            # Add back edges to represent looping. The forward edges are already
            # added by the bare task extractor. Any of the sink nodes need to
            # link back to the loop for the potential next iteration.
            for pred in inner_result.next_predecessors:
                self.context.graph.add_edge(pred, loop_node, rep.ORDER_BACK)

        # Sink node of a looping task is always the loop itself.
        # If the source list is empty, the task and its conditions will be skipped
        # entirely, so the loop would be followed by the next control node.
        # If it isn't empty, it'll always need to go back to the loop too.
        return inner_result.chain(ExtractionResult([loop_node], [], [loop_node]))

    def _extract_bare_task(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        tn = rep.Task(
            name=self.task.name, action=self.task.action, location=self.location
        )
        self.context.graph.add_node(tn)

        # If there's a condition: preds -> first condition -> ... last condition -> task
        # Otherwise: preds -> task -> rest
        condition_result = self.extract_condition(predecessors)
        first_node = (
            condition_result.added_control_nodes[0]
            if condition_result.added_control_nodes
            else tn
        )

        for condition_node in condition_result.next_predecessors:
            self.context.graph.add_edge(condition_node, tn, rep.ORDER)

        for pred in predecessors:
            self.context.graph.add_edge(pred, first_node, rep.ORDER)

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

        registered_vars = self._define_registered_var(tn)
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

        # Next predecessors are either any of the condition nodes, or the task node if all conditions passed.
        control_nodes = [tn] + [cn for cn in condition_result.added_control_nodes]
        return ExtractionResult(control_nodes, registered_vars, control_nodes)

    def _define_registered_var(self, task: rep.Task) -> Sequence[rep.Variable]:
        if not self.task.register:
            return []

        vn = self.context.vars.define_injected_variable(
            self.task.register, EnvironmentType.SET_FACTS_REGISTERED
        )
        self.context.graph.add_edge(task, vn, rep.DEF)
        return [vn]
