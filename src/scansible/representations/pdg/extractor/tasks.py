from __future__ import annotations

import abc

from ansible import constants as ansible_constants
from loguru import logger

from scansible.representations.structural import Task, TaskFile

from .. import representation as rep
from .context import ExtractionContext, TaskExtractionResult
from .var_context import ScopeLevel
from .variables import VariablesExtractor

_SENTINEL = object()

class TaskExtractor(abc.ABC):

    @abc.abstractclassmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]: ...

    def __init__(self, context: ExtractionContext, task: Task) -> None:
        self.context = context
        self.task = task
        self.location = rep.NodeLocation.fake()

    def extract_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
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
            tr = self.context.vars.evaluate_template(value, rep.NodeLocation.fake(), is_conditional)
            return tr.data_node
        else:
            return self.context.vars.add_literal(value, rep.NodeLocation.fake())

    def warn_remaining_kws(self, action: str = '') -> None:
        for other_kw, _ in self.task._get_non_default_attributes():
            if not other_kw in self.SUPPORTED_TASK_ATTRIBUTES() and other_kw != 'raw':
                self.context.graph.errors.append(f'Cannot handle {other_kw} on {action or self.task.action} yet!')


def task_extractor_factory(context: ExtractionContext, task: Task) -> TaskExtractor:
    action = task.action
    if action in ansible_constants._ACTION_SET_FACT:
        return SetFactTaskExtractor(context, task)
    if action in ansible_constants._ACTION_INCLUDE_VARS:
        return IncludeVarsTaskExtractor(context, task)
    if action in ansible_constants._ACTION_ALL_INCLUDE_IMPORT_TASKS:
        return IncludeTaskExtractor(context, task)

    return GenericTaskExtractor(context, task)

class GenericTaskExtractor(TaskExtractor):

    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:  # type: ignore[override]
        return frozenset({'name', 'action', 'args', 'vars', 'when', 'loop', 'loop_control', 'check_mode', 'register'})

    def extract_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        logger.debug(f'Extracting task with name {self.task.name!r} from {self.location}')
        with self.context.vars.enter_cached_scope(ScopeLevel.TASK_VARS):
            for var_name, var_value in self.task.vars.items():
                self.context.vars.register_variable(var_name, expr=var_value, level=ScopeLevel.TASK_VARS, name_location=self.location, init_location=self.location)

            if self.task.loop:
                result = self._extract_looping_task(predecessors)
            else:
                result = self._extract_single_task(predecessors)

            self.warn_remaining_kws('generic tasks')
            return result

    def _extract_single_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        if self.task.loop_control:
            self.context.graph.errors.append('Found loop_control without loop')
        tn, cn = self._extract_bare_task(predecessors)
        added_var = self._define_registered_var([tn])
        added: list[rep.ControlNode] = [tn]
        # Condition could be false, so the task could be skipped and the
        # condition itself could also be a predecessor.
        if cn is not None:
            added.append(cn)
        return TaskExtractionResult(
                next_predecessors=added,
                added_variable_nodes=[] if added_var is None else [added_var],
                added_control_nodes=added)

    def _extract_looping_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        loop_node = rep.Loop(location=self.location)
        source_and_name = self.extract_looping_value_and_name()
        assert source_and_name is not None, 'Internal error'

        loop_source_var, loop_var_name = source_and_name
        self.context.graph.add_node(loop_node)
        self.context.graph.add_edge(loop_source_var, loop_node, rep.USE)
        for pred in predecessors:
            self.context.graph.add_edge(pred, loop_node, rep.ORDER)

        # For some reason, loop vars have the same precedence as include params.
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.register_variable(loop_var_name, ScopeLevel.INCLUDE_PARAMS, name_location=self.location, init_location=self.location)
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

        # Any registered variable is defined both by the loop and the individual tasks
        added_var = self._define_registered_var([loop_node, tn])

        # It could be that the source list is empty, in which case the task will
        # be skipped and there will be a direct edge from the loop to the next
        # task. If it isn't skipped, it'll always have to go back to the loop
        # too
        return TaskExtractionResult(
                added_control_nodes=[loop_node, tn] + ([cn] if cn is not None else []),
                added_variable_nodes=[] if added_var is None else [added_var],
                next_predecessors=[loop_node])


    def _extract_bare_task(self, predecessors: list[rep.ControlNode]) -> tuple[rep.Task, rep.Conditional | None]:
        tn = rep.Task(name=self.task.name, action=self.task.action, location=self.location)
        cn: rep.Conditional | None = None
        first_node: rep.ControlNode = tn
        self.context.graph.add_node(tn)

        if (condition_val_node := self.extract_conditional_value()) is not None:
            # Add a conditional node, which uses the expression IV, and is
            # succeeded by the task itself.
            cn = rep.Conditional(location=self.location)
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
            vn = self.context.vars.register_variable(registered_var_name, ScopeLevel.SET_FACTS_REGISTERED, name_location=self.location, init_location=self.location)
            self.context.graph.add_node(vn)
            # There could be multiple defining control nodes, e.g. the loop node and the task node.
            for definer in definers:
                self.context.graph.add_edge(definer, vn, rep.DEF)
            return vn
        return None

class SetFactTaskExtractor(TaskExtractor):
    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:  # type: ignore[override]
        return frozenset({'name', 'action', 'args', 'when', 'loop', 'loop_control'})

    def extract_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        if self.task.loop:
            return self._extract_looping_task(predecessors)
        return self._extract_bare_task(predecessors)

    def _extract_bare_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        with self.context.vars.enter_cached_scope(ScopeLevel.TASK_VARS):
            # Evaluate all values before defining the variables. Ansible does
            # the same. We need to do this as one variable may be defined in
            # terms of another variable that's `set_fact`ed
            name_to_value = {var_name: self.extract_value(var_value) for var_name, var_value in self.task.args.items()}
            added_vars: list[rep.Variable] = []
            cond_val = self.extract_conditional_value()
            for var_name, value_node in name_to_value.items():
                var_node = self.context.vars.register_variable(var_name, ScopeLevel.SET_FACTS_REGISTERED, name_location=self.location, init_location=self.location)
                added_vars.append(var_node)
                self.context.graph.add_node(var_node)
                self.context.graph.add_edge(value_node, var_node, rep.DEF)
                if cond_val is not None:
                    self.context.graph.add_edge(cond_val, var_node, rep.DEFINED_IF)

        self.warn_remaining_kws()
        return TaskExtractionResult(added_control_nodes=[], added_variable_nodes=added_vars, next_predecessors=predecessors)

    def _extract_looping_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        self.context.graph.errors.append('loops on set_fact are not fully supported yet')
        source_and_name = self.extract_looping_value_and_name()
        assert source_and_name is not None, 'Internal error'

        loop_source_var, loop_var_name = source_and_name
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.register_variable(loop_var_name, ScopeLevel.INCLUDE_PARAMS, name_location=self.location, init_location=self.location)
            self.context.graph.add_edge(loop_source_var, loop_target_var, rep.DEF_LOOP_ITEM)

            return self._extract_bare_task(predecessors)

class IncludeVarsTaskExtractor(TaskExtractor):
    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:  # type: ignore[override]
        return frozenset({'name', 'action', 'args', 'when'})

    def extract_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        args = dict(self.task.args)
        abort_result = TaskExtractionResult(added_control_nodes=[], added_variable_nodes=[], next_predecessors=predecessors)

        incl_name = args.pop('_raw_params', '')
        if not incl_name or not isinstance(incl_name, str):
            self.context.graph.errors.append(f'Unknown included file name!')
            return abort_result

        if args:
            self.context.graph.errors.append(f'Additional arguments on included vars action')

        if '{{' in incl_name:
            # TODO: When we do handle expressions here, we should make sure
            # to check whether these expressions can or cannot use the include
            # parameters. If they cannot, we should extract the included
            # name before registering the variables.
            self.context.graph.errors.append(f'Cannot handle dynamic file name on {self.task.action} yet!')
            return abort_result

        varfile = self.context.include_ctx.load_var_file(incl_name)

        if not varfile:
            self.context.graph.errors.append(f'Var file not found: {incl_name}')
            return abort_result

        cond_node = self.extract_conditional_value()
        inner_result = VariablesExtractor(self.context, varfile.variables, self.location).extract_variables(ScopeLevel.INCLUDE_VARS)
        if cond_node is not None:
            for added_var in inner_result.added_variable_nodes:
                self.context.graph.add_edge(cond_node, added_var, rep.DEFINED_IF)

        self.warn_remaining_kws()
        return TaskExtractionResult(added_control_nodes=[], added_variable_nodes=inner_result.added_variable_nodes, next_predecessors=predecessors)

class IncludeTaskExtractor(TaskExtractor):
    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:  # type: ignore[override]
        return frozenset({'name', 'action', 'args', 'when'})

    def extract_task(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            for var_name, var_value in self.task.vars.items():
                self.context.vars.register_variable(var_name, expr=var_value, level=ScopeLevel.INCLUDE_PARAMS, name_location=self.location, init_location=self.location)

            abort_result = TaskExtractionResult(added_control_nodes=[], added_variable_nodes=[], next_predecessors=predecessors)

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
            with self.context.include_ctx.load_and_enter_task_file(incl_name) as task_file:
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
                    cn: rep.ControlNode = rep.Conditional(location=self.location)
                    self.context.graph.add_node(cn)
                    self.context.graph.add_edge(cond_val_node, cn, rep.USE)
                    for pred in predecessors:
                        self.context.graph.add_edge(pred, cn, rep.ORDER)
                    include_predecessors = [cn]
                else:
                    include_predecessors = predecessors
                self.warn_remaining_kws()

                # Delayed import to prevent circular imports. task_files imports
                # blocks, which in turn imports this module.
                from .task_lists import TaskListExtractor
                inner_result = TaskListExtractor(self.context, task_file.tasks).extract_tasks(include_predecessors)  # type: ignore[arg-type]

            if cond_val_node is None:
                return inner_result

            # Need to link up condition to defined variables, and add condition
            # to next predecessors as the include may be skipped.
            for added_var in inner_result.added_variable_nodes:
                self.context.graph.add_edge(cond_val_node, added_var, rep.DEFINED_IF)
            return TaskExtractionResult(
                added_control_nodes=[cn] + inner_result.added_control_nodes,
                added_variable_nodes=inner_result.added_variable_nodes,
                next_predecessors=[cn] + inner_result.next_predecessors)
