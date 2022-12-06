from __future__ import annotations

from collections.abc import Sequence

from loguru import logger

from ... import representation as rep
from ..result import ExtractionResult
from ..var_context import ScopeLevel
from .base import TaskExtractor


class IncludeTaskExtractor(TaskExtractor):

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.setup_task_vars_scope(ScopeLevel.INCLUDE_PARAMS):
            abort_result = ExtractionResult.empty(predecessors)

            args = dict(self.task.args)
            incl_name = args.pop('_raw_params', '')
            if not incl_name or not isinstance(incl_name, str):
                self.context.graph.errors.append(f'Unknown included file name!')
                return abort_result

            if '{{' in incl_name:
                # TODO: When we do handle expressions here, we should make sure
                # to check whether these expressions can or cannot use the include
                # parameters. If they cannot, we should extract the included
                # name before registering the variables.
                self.context.graph.errors.append(f'Cannot handle dynamic file name on {self.task.action} yet!')
                return abort_result

            if args:
                # Still arguments left?
                self.context.graph.errors.append('Superfluous arguments on include/import task!')
                logger.debug(args)

            logger.debug(incl_name)
            with self.context.include_ctx.load_and_enter_task_file(incl_name, self.location) as task_file:
                if not task_file:
                    self.context.graph.errors.append(f'Task file not found: {incl_name}')
                    return abort_result

                cond_val_node: rep.DataNode | None
                if self.task.action == 'import_tasks' and self.extract_conditional_value() is not None:
                    self.context.graph.errors.append('Not sure how to handle conditional on static import')
                    cond_val_node = None
                else:
                    cond_val_node = self.extract_conditional_value()

                if cond_val_node is not None:
                    # Add a conditional node, which uses the expression IV, and is
                    # succeeded by the task itself.
                    cn: rep.ControlNode = rep.Conditional(location=self.context.get_location(self.task.when) or self.location)
                    self.context.graph.add_node(cn)
                    self.context.graph.add_edge(cond_val_node, cn, rep.USE)
                    for pred in predecessors:
                        self.context.graph.add_edge(pred, cn, rep.ORDER)
                    predecessors = [cn]

                self.warn_remaining_kws()

                # Delayed import to prevent circular imports. task_files imports
                # blocks, which in turn imports this module.
                from ..task_lists import TaskListExtractor
                result = TaskListExtractor(self.context, task_file.tasks).extract_tasks(predecessors)  # type: ignore[arg-type]

            if cond_val_node is not None:
                # Need to link up condition to defined variables, and add condition
                # to next predecessors as the include may be skipped.
                for added_var in result.added_variable_nodes:
                    self.context.graph.add_edge(cond_val_node, added_var, rep.DEFINED_IF)

                return result.add_control_nodes(cn).add_next_predecessors(cn)
            return result
