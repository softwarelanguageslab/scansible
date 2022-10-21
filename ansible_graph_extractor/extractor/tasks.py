from __future__ import annotations

from loguru import logger

from voyager.models.structural.role import Task, TaskFile

from ..models import nodes as n
from ..models import edges as e
from .context import ExtractionContext, TaskExtractionResult
from .var_context import ScopeLevel
from .var_files import VariableFileExtractor

_SENTINEL = object()

class TaskExtractor:

    def __init__(self, context: ExtractionContext, task: Task) -> None:
        self.context = context
        self.task = task
        self.kws = dict(self.task._raw_kws)
        self.name = self.kws.pop('name', '')
        self.action = self.kws.pop('action')
        self.location = f'{task.position_file_name}:{task.position_line_number}:{task.position_column_number}'

    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        raise NotImplementedError('To be implemented by subclass')

    def extract_conditional_value(self) -> n.DataNode | None:
        if (condition := self.kws.pop('when', _SENTINEL)) is not _SENTINEL:
            if not isinstance(condition, str):
                self.context.graph.errors.append(f'Cannot handle {type(condition)} conditionals yet!')
            else:
                return self.extract_value(condition, is_conditional=True)

        return None

    def extract_looping_value_and_name(self) -> tuple[n.DataNode, str] | None:
        loop_expr = self.kws.pop('loop', _SENTINEL)
        if loop_expr is _SENTINEL:
            return None

        loop_source_var = self.extract_value(loop_expr)

        # Create a copy of the loop_control in case this loop could be evaluated
        # multiple times, to ensure we don't remove loop information
        loop_control = dict(self.kws.pop('loop_control', {}))
        if 'loop_with' in self.kws:
            self.context.graph.errors.append(f'I cannot handle looping style "{self.kws["loop_with"]}" yet!')
        loop_var_name = loop_control.pop('loop_var', 'item')
        for loop_control_k in loop_control:
            self.context.graph.errors.append(f'I cannot handle loop_control option {loop_control_k} yet!')

        return loop_source_var, loop_var_name

    # TODO: This doesn't really belong here...
    def extract_value(self, value: str | list | int | float | dict | bool, is_conditional: bool = False) -> n.DataNode:  # type: ignore[type-arg]
        if isinstance(value, str):
            tr = self.context.vars.evaluate_template(value, is_conditional)
            return tr.data_node

        type_ = value.__class__.__name__
        if isinstance(value, (dict, list)):
            self.context.graph.errors.append('I am not able to handle composite literals yet')
            lit = n.Literal(node_id=self.context.next_id(), type=type_, value='')
        else:
            lit = n.Literal(node_id=self.context.next_id(),type=type_, value=value)

        self.context.graph.add_node(lit)
        return lit

    def warn_remaining_kws(self, action: str = '') -> None:
        for other_kw in self.kws:
            self.context.graph.errors.append(f'Cannot handle {other_kw} on {action or self.action} yet!')


def task_extractor_factory(context: ExtractionContext, task: Task) -> TaskExtractor:
    action = task.action  # type: ignore[attr-defined]
    if action == 'set_fact':
        return SetFactTaskExtractor(context, task)
    if action == 'include_vars':
        return IncludeVarsTaskExtractor(context, task)
    if action in ('import_tasks', 'include_tasks'):
        return IncludeTaskExtractor(context, task)

    return GenericTaskExtractor(context, task)

class GenericTaskExtractor(TaskExtractor):
    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        logger.debug(f'Extracting task with name "{self.name}" from "{self.location}"')
        with self.context.vars.enter_cached_scope(ScopeLevel.TASK_VARS):
            for var_name, var_value in self.kws.pop('vars', {}).items():
                self.context.vars.register_variable(var_name, expr=var_value, level=ScopeLevel.TASK_VARS, location=self.location)

            if 'loop' in self.kws:
                result = self._extract_looping_task(predecessors)
            else:
                result = self._extract_single_task(predecessors)

            self.warn_remaining_kws('generic tasks')
            return result

    def _extract_single_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        if 'loop_control' in self.kws:
            self.context.graph.errors.append('Found loop_control without loop')
        tn, cn = self._extract_bare_task(predecessors)
        added_var = self._define_registered_var([tn])
        added: list[n.ControlNode] = [tn]
        # Condition could be false, so the task could be skipped and the
        # condition itself could also be a predecessor.
        if cn is not None:
            added.append(cn)
        return TaskExtractionResult(
                next_predecessors=added,
                added_variable_nodes=[] if added_var is None else [added_var],
                added_control_nodes=added)

    def _extract_looping_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        loop_node = n.Loop(node_id=self.context.next_id(), location=self.location)
        source_and_name = self.extract_looping_value_and_name()
        assert source_and_name is not None, 'Internal error'

        loop_source_var, loop_var_name = source_and_name
        self.context.graph.add_edge(loop_source_var, loop_node, e.USE)
        for pred in predecessors:
            self.context.graph.add_edge(pred, loop_node, e.ORDER)

        # For some reason, loop vars have the same precedence as include params.
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.register_variable(loop_var_name, ScopeLevel.INCLUDE_PARAMS, location=self.location)
            self.context.graph.add_edge(loop_source_var, loop_target_var, e.DEF_LOOP_ITEM)

            tn, cn = self._extract_bare_task([loop_node])
            # Back edge to represent looping. Forward edge already added by the
            # called method.
            self.context.graph.add_edge(tn, loop_node, e.ORDER_BACK)
            # If there was a conditional node added by the task, its "else" branch
            # needs to link back to the loop. If a loop step is skipped, the next
            # task will be the next step in the loop.
            if cn is not None:
                self.context.graph.add_edge(cn, loop_node, e.ORDER_BACK)

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


    def _extract_bare_task(self, predecessors: list[n.ControlNode]) -> tuple[n.Task, n.Conditional | None]:
        tn = n.Task(node_id=self.context.next_id(), name=self.name, action=self.action, location=self.location)
        cn: n.Conditional | None = None
        first_node: n.ControlNode = tn
        self.context.graph.add_node(tn)

        if (condition_val_node := self.extract_conditional_value()) is not None:
            # Add a conditional node, which uses the expression IV, and is
            # succeeded by the task itself.
            cn = n.Conditional(node_id=self.context.next_id(), location=self.location)
            self.context.graph.add_node(cn)
            self.context.graph.add_edge(condition_val_node, cn, e.USE)
            self.context.graph.add_edge(cn, tn, e.ORDER)
            first_node = cn

        for pred in predecessors:
            self.context.graph.add_edge(pred, first_node, e.ORDER)

        # Link data flow
        for arg_name, arg_value in self.kws.pop('args', {}).items():
            arg_node = self.extract_value(arg_value)
            self.context.graph.add_edge(arg_node, tn, e.Keyword(keyword=f'args.{arg_name}'))

        misc_kws = {'check_mode',}
        for misc_kw in misc_kws:
            if (kw_val := self.kws.pop(misc_kw, _SENTINEL)) is not _SENTINEL:
                val_node = self.extract_value(kw_val)
                self.context.graph.add_edge(val_node, tn, e.Keyword(keyword=misc_kw))

        return tn, cn

    def _define_registered_var(self, definers: list[n.ControlNode]) -> n.Variable | None:
        if (registered_var_name := self.kws.pop('register', _SENTINEL)) is not _SENTINEL:
            assert isinstance(registered_var_name, str)
            vn = self.context.vars.register_variable(registered_var_name, ScopeLevel.SET_FACTS_REGISTERED, location=self.location)
            self.context.graph.add_node(vn)
            # There could be multiple defining control nodes, e.g. the loop node and the task node.
            for definer in definers:
                self.context.graph.add_edge(definer, vn, e.DEF)
            return vn
        return None

class SetFactTaskExtractor(TaskExtractor):
    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        if 'loop' in self.kws:
            return self._extract_looping_task(predecessors)
        return self._extract_bare_task(predecessors)

    def _extract_bare_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        with self.context.vars.enter_cached_scope(ScopeLevel.TASK_VARS):
            # Evaluate all values before defining the variables. Ansible does
            # the same. We need to do this as one variable may be defined in
            # terms of another variable that's `set_fact`ed
            name_to_value = {var_name: self.extract_value(var_value) for var_name, var_value in self.kws.pop('args').items()}
            added_vars: list[n.Variable] = []
            cond_val = self.extract_conditional_value()
            for var_name, value_node in name_to_value.items():
                var_node = self.context.vars.register_variable(var_name, ScopeLevel.SET_FACTS_REGISTERED, location=self.location)
                added_vars.append(var_node)
                self.context.graph.add_node(var_node)
                self.context.graph.add_edge(value_node, var_node, e.DEF)
                if cond_val is not None:
                    self.context.graph.add_edge(cond_val, var_node, e.DEFINED_IF)

        self.warn_remaining_kws()
        return TaskExtractionResult(added_control_nodes=[], added_variable_nodes=added_vars, next_predecessors=predecessors)

    def _extract_looping_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        source_and_name = self.extract_looping_value_and_name()
        assert source_and_name is not None, 'Internal error'

        loop_source_var, loop_var_name = source_and_name
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.register_variable(loop_var_name, ScopeLevel.INCLUDE_PARAMS, location=self.location)
            self.context.graph.add_edge(loop_source_var, loop_target_var, e.DEF_LOOP_ITEM)

            return self._extract_bare_task(predecessors)

class IncludeVarsTaskExtractor(TaskExtractor):
    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        args = self.kws.pop('args', {})
        abort_result = TaskExtractionResult(added_control_nodes=[], added_variable_nodes=[], next_predecessors=predecessors)

        incl_name = args.pop('_raw_params', '')
        if not incl_name:
            self.context.graph.errors.append(f'Unknown included file name!')
            return abort_result

        if args:
            self.context.graph.errors.append(f'Additional arguments on included vars action')

        if '{{' in incl_name:
            # TODO: When we do handle expressions here, we should make sure
            # to check whether these expressions can or cannot use the include
            # parameters. If they cannot, we should extract the included
            # name before registering the variables.
            self.context.graph.errors.append(f'Cannot handle dynamic file name on {self.action} yet!')
            return abort_result

        varfile = self.context.files.find_var_file(incl_name) if not self.context.is_pb else self.context.play.get_vars_file(incl_name)

        if not varfile:
            self.context.graph.errors.append(f'Var file not found: {incl_name}')
            return abort_result

        cond_node = self.extract_conditional_value()
        var_location = f'{varfile.file_name} via {self.location}'
        inner_result = VariableFileExtractor(self.context, varfile, var_location).extract_variables(ScopeLevel.INCLUDE_VARS)
        if cond_node is not None:
            for added_var in inner_result.added_variable_nodes:
                self.context.graph.add_edge(cond_node, added_var, e.DEFINED_IF)

        self.warn_remaining_kws()
        return TaskExtractionResult(added_control_nodes=[], added_variable_nodes=inner_result.added_variable_nodes, next_predecessors=predecessors)

class IncludeTaskExtractor(TaskExtractor):
    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            for var_name, var_value in self.kws.pop('vars', {}).items():
                self.context.vars.register_variable(var_name, expr=var_value, level=ScopeLevel.INCLUDE_PARAMS, location=self.location)

            abort_result = TaskExtractionResult(added_control_nodes=[], added_variable_nodes=[], next_predecessors=predecessors)

            args = self.kws.pop('args', {})
            incl_name = args.pop('_raw_params', '')
            if not incl_name:
                self.context.graph.errors.append(f'Unknown included file name!')
                return abort_result

            if '{{' in incl_name:
                # TODO: When we do handle expressions here, we should make sure
                # to check whether these expressions can or cannot use the include
                # parameters. If they cannot, we should extract the included
                # name before registering the variables.
                self.context.graph.errors.append(f'Cannot handle dynamic file name on {self.action} yet!')
                return abort_result

            if args:
                # Still arguments left?
                self.context.graph.errors.append('Superfluous arguments on include/import task!')
                logger.debug(args)

            logger.debug(incl_name)
            task_file = self.context.files.find_task_file(incl_name) if not self.context.is_pb else self.context.play.get_tasks_file(incl_name)
            if not task_file:
                self.context.graph.errors.append(f'Task file not found: {incl_name}')
                return abort_result

            cond_val_node: n.DataNode | None
            if self.action == 'import_tasks' and self.extract_conditional_value() is not None:
                self.context.graph.errors.append('Not sure how to handle conditional on static import')
                cond_val_node = None
            else:
                cond_val_node = self.extract_conditional_value()

            if cond_val_node is not None:
                # Add a conditional node, which uses the expression IV, and is
                # succeeded by the task itself.
                cn: n.ControlNode = n.Conditional(node_id=self.context.next_id(), location=self.location)
                self.context.graph.add_node(cn)
                self.context.graph.add_edge(cond_val_node, cn, e.USE)
                for pred in predecessors:
                    self.context.graph.add_edge(pred, cn, e.ORDER)
                include_predecessors = [cn]
            else:
                include_predecessors = predecessors
            self.warn_remaining_kws()

            # Delayed import to prevent circular imports. task_files imports
            # blocks, which in turn imports this module.
            from .task_files import TaskFileExtractor
            with self.context.files.enter_included_file(task_file):
                inner_result = TaskFileExtractor(self.context, task_file).extract_tasks(include_predecessors)

            if cond_val_node is None:
                return inner_result

            # Need to link up condition to defined variables, and add condition
            # to next predecessors as the include may be skipped.
            for added_var in inner_result.added_variable_nodes:
                self.context.graph.add_edge(cond_val_node, added_var, e.DEFINED_IF)
            return TaskExtractionResult(
                added_control_nodes=[cn] + inner_result.added_control_nodes,
                added_variable_nodes=inner_result.added_variable_nodes,
                next_predecessors=[cn] + inner_result.next_predecessors)
