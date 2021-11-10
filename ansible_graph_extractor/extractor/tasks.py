from __future__ import annotations

from loguru import logger

from voyager.models.structural.role import Task

from ..models import nodes as n
from ..models import edges as e
from .context import ExtractionContext, TaskExtractionResult, get_file_name
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

    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        raise NotImplementedError('To be implemented by subclass')

    # TODO: This doesn't really belong here...
    def extract_value(self, value: str | list | int | float | dict | bool, is_conditional: bool = False) -> n.DataNode:  # type: ignore[type-arg]
        if isinstance(value, str):
            tr = self.context.vars.evaluate_template(value, self.context.graph, is_conditional)
            return tr.data_node

        type_ = value.__class__.__name__
        if isinstance(value, (dict, list)):
            self.context.graph.errors.append('I am not able to handle composite literals yet')
            lit = n.Literal(node_id=self.context.next_id(), type=type_, value='')
        else:
            lit = n.Literal(node_id=self.context.next_id(),type=type_, value=value)

        self.context.graph.add_node(lit)
        return lit


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
        logger.debug(f'Extracting task with name "{self.name}"')
        with self.context.vars.enter_scope(ScopeLevel.TASK_VARS):
            for var_name, var_value in self.kws.pop('vars', {}).items():
                self.context.vars.register_variable(var_name, expr=var_value, graph=self.context.graph, level=ScopeLevel.TASK_VARS)

            if 'loop' in self.kws:
                result = self._extract_looping_task(predecessors)
            else:
                result = self._extract_single_task(predecessors)

            for kw in self.kws.keys():
                self.context.graph.errors.append(f'I do not know how to handle {kw} on generic tasks')

            return result

    def _extract_single_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        if 'loop_control' in self.kws:
            self.context.graph.errors.append('Found loop_control without loop')
        tn, cn = self._extract_bare_task(predecessors)
        self._define_registered_var([tn])
        added: list[n.ControlNode] = [tn]
        # Condition could be false, so the task could be skipped and the
        # condition itself could also be a predecessor.
        if cn is not None:
            added.append(cn)
        return TaskExtractionResult(next_predecessors=added, added_control_nodes=added)

    def _extract_looping_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        loop_node = n.Loop(node_id=self.context.next_id())
        loop_source_var = self.extract_value(self.kws.pop('loop'))
        self.context.graph.add_edge(loop_source_var, loop_node, e.USE)
        for pred in predecessors:
            self.context.graph.add_edge(pred, loop_node, e.ORDER)

        if 'loop_control' in self.kws:
            self.context.graph.errors.append('I cannot handle custom loops yet!')
        if 'loop_with' in self.kws:
            self.context.graph.errors.append(f'I cannot handle looping style "{self.kws["loop_with"]}" yet!')

        # For some reason, loop vars have the same precedence as include params.
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.register_variable('item', ScopeLevel.INCLUDE_PARAMS, graph=self.context.graph)
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
        self._define_registered_var([loop_node, tn])

        # It could be that the source list is empty, in which case the task will
        # be skipped and there will be a direct edge from the loop to the next
        # task. If it isn't skipped, it'll always have to go back to the loop
        # too
        return TaskExtractionResult(
                added_control_nodes=[loop_node, tn] + ([cn] if cn is not None else []),
                next_predecessors=[loop_node])


    def _extract_bare_task(self, predecessors: list[n.ControlNode]) -> tuple[n.Task, n.Conditional | None]:
        tn = n.Task(node_id=self.context.next_id(), name=self.name, action=self.action)
        cn: n.Conditional | None = None
        first_node: n.ControlNode = tn
        self.context.graph.add_node(tn)

        if (condition := self.kws.pop('when', _SENTINEL)) is not _SENTINEL:
            if not isinstance(condition, str):
                self.context.graph.errors.append(f'Cannot handle {type(condition)} conditionals yet!')
            else:
                # Add a conditional node, which uses the expression IV, and is
                # succeeded by the task itself.
                cn = n.Conditional(node_id=self.context.next_id())
                self.context.graph.add_node(cn)
                condition_val_node = self.extract_value(condition, is_conditional=True)
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

    def _define_registered_var(self, definers: list[n.ControlNode]) -> None:
        if (registered_var_name := self.kws.pop('register', _SENTINEL)) is not _SENTINEL:
            assert isinstance(registered_var_name, str)
            vn = self.context.vars.register_variable(registered_var_name, ScopeLevel.SET_FACTS_REGISTERED, graph=self.context.graph)
            self.context.graph.add_node(vn)
            # There could be multiple defining control nodes, e.g. the loop node and the task node.
            for definer in definers:
                self.context.graph.add_edge(definer, vn, e.DEF)

class SetFactTaskExtractor(TaskExtractor):
    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        for var_name, var_value in self.kws.pop('args').items():
            value_n = self.extract_value(var_value)
            vn = self.context.vars.register_variable(var_name, ScopeLevel.SET_FACTS_REGISTERED, graph=self.context.graph)

            self.context.graph.add_node(vn)
            self.context.graph.add_edge(value_n, vn, e.DEF)

        for other_kw in self.kws:
            self.context.graph.errors.append(f'Cannot handle {other_kw} on set_fact yet!')

        return TaskExtractionResult(added_control_nodes=[], next_predecessors=predecessors)

class IncludeVarsTaskExtractor(TaskExtractor):
    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        args = self.kws.pop('args', {})
        for other_kw in self.kws:
            self.context.graph.errors.append(f'Cannot handle {other_kw} on {self.action} yet!')

        result = TaskExtractionResult(added_control_nodes=[], next_predecessors=predecessors)

        incl_name = args.pop('_raw_params', '')
        if not incl_name:
            self.context.graph.errors.append(f'Unknown included file name!')
            return result

        if args:
            self.context.graph.errors.append(f'Additional arguments on included vars action')

        if '{{' in incl_name:
            # TODO: When we do handle expressions here, we should make sure
            # to check whether these expressions can or cannot use the include
            # parameters. If they cannot, we should extract the included
            # name before registering the variables.
            self.context.graph.errors.append(f'Cannot handle dynamic file name on {self.action} yet!')
            return result

        folder, *_ = incl_name.split('/', 1)
        name = get_file_name(incl_name)
        if folder not in ('vars', 'defaults'):
            self.context.graph.errors.append(f'Unsupported folder for {self.action}: {folder}')
            return result

        varfile_store = self.context.files.var_files if folder == 'vars' else self.context.files.defaults_files
        varfile = varfile_store.get(name)  # type: ignore[attr-defined]

        if not varfile:
            self.context.graph.errors.append(f'Var file not found: {incl_name}')
            return result

        VariableFileExtractor(self.context, varfile).extract_variables(ScopeLevel.INCLUDE_VARS)
        return result

class IncludeTaskExtractor(TaskExtractor):
    def extract_task(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            for var_name, var_value in self.kws.pop('vars', {}).items():
                self.context.vars.register_variable(var_name, expr=var_value, level=ScopeLevel.INCLUDE_PARAMS, graph=self.context.graph)

            abort_result = TaskExtractionResult(added_control_nodes=[], next_predecessors=predecessors)

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

            for other_kw in self.kws:
                self.context.graph.errors.append(f'Cannot handle {other_kw} on {self.action} yet!')

            logger.debug(incl_name)
            filename = get_file_name(incl_name)
            task_file = self.context.files.task_files.get(filename)
            if not task_file:
                self.context.graph.errors.append(f'Task file not found: {filename}')
                return abort_result

            # Delayed import to prevent circular imports. task_files imports
            # blocks, which in turn imports this module.
            from .task_files import TaskFileExtractor
            return TaskFileExtractor(self.context, task_file).extract_tasks(predecessors)
