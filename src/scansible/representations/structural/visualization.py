from typing import Any, Mapping, Sequence

import textwrap
from pathlib import Path

import graphviz as gv

from . import representation as rep


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, Path, rep.VaultValue)) or not value

def _escape_html(s: str) -> str:
    return gv.nohtml(s).replace('<', '&lt;').replace('>', '&gt;')


def _create_record_row(attr_name: str, attr_value: Any) -> str:
    prefix = f'{attr_name}: <I>{type(attr_value).__name__}</I>'
    attr_value_label = '<BR/>'.join(textwrap.wrap(_escape_html(str(attr_value)), width=40))
    if (isinstance(attr_value, str) and attr_value) or isinstance(attr_value, (int, float, bool, Path, rep.VaultValue)):
        attr_label = f'{prefix}<BR/>{attr_value_label}'
    elif not attr_value:
        attr_label = f'{prefix}<BR/>&#8709;'
    else:
        attr_label = prefix

    return f'<TR><TD PORT="{attr_name}">{attr_label}</TD></TR>'

def _create_record(name: str, *attrs: tuple[str, Any]) -> str:
    attr_rows = ''.join(_create_record_row(attr_name, attr_value) for attr_name, attr_value in attrs)
    return f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4"><TR><TD><B>{name}</B></TD></TR>{attr_rows}</TABLE>>'


def _create_list(length: int) -> str:
    tds = ''.join(f'<TD PORT="e{i}"></TD>' for i in range(length))
    return f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4"><TR>{tds}</TR></TABLE>>'


class VisualizationVisitor:

    def __init__(self) -> None:
        self.full_graph = gv.Digraph()
        self.full_graph.attr(rankdir='LR', fontname='Menlo')
        self.full_graph.attr('node', shape='none', fontname='Menlo')
        # current subgraph
        self.g = self.full_graph
        self._id_counter = 0

    def _next_id(self) -> str:
        self._id_counter += 1
        return f'n{self._id_counter}'

    def add_node(self, label: str, **attrs: str) -> str:
        node_id = self._next_id()
        self.g.node(node_id, label, **attrs)
        return node_id

    def visit_raw(self, v: Mapping[Any, Any] | Sequence[Any]) -> str:
        if isinstance(v, dict):
            dct_id = self.add_node(_create_record('dict', *v.items()))
            for key, value in v.items():
                if _is_scalar(value):
                    # Already in-line in dict node
                    continue
                child_id = self.visit_raw(value)
                self.g.edge(f'{dct_id}:{key}', child_id)
            return dct_id

        assert isinstance(v, list), f'Unsupported type: {type(v)}'
        lst_id = self.add_node(_create_list(len(v)))
        for child_idx, child in enumerate(v):
            if _is_scalar(child):
                child_val_label = _escape_html(str(child)) if (isinstance(child, str) and child) or isinstance(child, (int, float, bool, Path, rep.VaultValue)) else '&#8709'
                child_label = f'<<I>{type(child).__name__}</I><BR/>{child_val_label}>'
                child_id = self.add_node(child_label, shape='box')
            else:
                child_id = self.visit_raw(child)
            self.g.edge(f'{lst_id}:e{child_idx}', child_id)
        return lst_id

    def visit_multi_structural_model(self, v: rep.MultiStructuralModel) -> str:
        self.g.attr(label='<Structural models for <B>{v.id}</B>')

        for version, model in v.structural_models.items():
            # Make sure the name of the subgraph starts with `cluster` so that
            # the rendering engine groups the nodes together.
            with self.g.subgraph(name=f'cluster_{version}') as subg:
                self.g = subg
                model.accept(self)

        return ''

    def visit_structural_model(self, v: rep.StructuralModel) -> str:
        self.g.attr(label=f'<Structural model for <B>{v.id}</B>, version <B>{v.version}</B><br/>{v.path}>')
        v.root.accept(self)
        return ''

    def visit_playbook(self, v: rep.Playbook) -> str:
        pb_id = self.add_node(_create_record('Playbook', ('plays', v.plays)))
        self.g.edges((f'{pb_id}:plays', play.accept(self)) for play in v.plays)
        return pb_id

    def visit_play(self, v: rep.Play) -> str:
        p_id = self.add_node(_create_record('Play', *v._yield_non_default_representable_attributes()))
        special_directives = ('tasks', 'roles', 'pre_tasks', 'post_tasks', 'handlers', 'vars_prompt')

        for attr_name, attr_value in v._yield_non_default_representable_attributes():
            if _is_scalar(attr_value):
                continue
            if attr_name in special_directives:
                attr_id = self.add_node(_create_list(len(attr_value)))
                for child_idx, child in enumerate(attr_value):
                    self.g.edge(f'{attr_id}:e{child_idx}', child.accept(self))
            else:
                attr_id = self.visit_raw(attr_value)
            self.g.edge(f'{p_id}:{attr_name}', attr_id)

        return p_id

    def visit_role(self, v: rep.Role) -> str:
        r_id = self.add_node(_create_record(
                'Role',
                ('meta_file', v.meta_file),
                ('default_var_files', v.default_var_files),
                ('role_var_files', v.role_var_files),
                ('task_files', v.task_files),
                ('handler_files', v.handler_files)))

        if v.meta_file is not None:
            self.g.edge(f'{r_id}:meta_file', v.meta_file.accept(self))

        for attr in ('default_var_files', 'role_var_files', 'task_files', 'handler_files'):
            attr_value = getattr(v, attr)
            if not attr_value:
                continue

            dct_id = self.add_node(_create_record('dict', *attr_value.items()))
            self.g.edge(f'{r_id}:{attr}', dct_id)

            for file_name, file in attr_value.items():
                self.g.edge(f'{dct_id}:{file_name}', file.accept(self))

        return r_id

    def visit_meta_file(self, v: rep.MetaFile) -> str:
        mf_id = self.add_node(_create_record('MetaFile', *v._yield_non_default_representable_attributes()))
        self.g.edge(f'{mf_id}:metablock', v.metablock.accept(self))
        return mf_id

    def visit_meta_block(self, v: rep.MetaBlock) -> str:
        mb_id = self.add_node(_create_record('MetaBlock', *v._yield_non_default_representable_attributes()))

        for attr in ('platforms', 'dependencies'):
            attr_value = getattr(v, attr)
            if not attr_value:
                continue

            lst_id = self.add_node(_create_list(len(attr_value)))
            for child_idx, child in enumerate(attr_value):
                self.g.edge(f'{lst_id}:e{child_idx}', child.accept(self))
            self.g.edge(f'{mb_id}:{attr}', lst_id)

        return mb_id

    def visit_task_file(self, v: rep.TaskFile) -> str:
        tf_id = self.add_node(_create_record('TaskFile', *v._yield_non_default_representable_attributes()))
        if v.tasks:
            tasks_id = self.add_node(_create_list(len(v.tasks)))
            self.g.edge(f'{tf_id}:tasks', tasks_id)
            for child_idx, child in enumerate(v.tasks):
                self.g.edge(f'{tasks_id}:e{child_idx}', child.accept(self))

        return tf_id

    def visit_block(self, v: rep.Block) -> str:
        b_id = self.add_node(_create_record('Block', *v._yield_non_default_representable_attributes()))
        special_directives = ('block', 'rescue', 'always')

        for attr_name, attr_value in v._yield_non_default_representable_attributes():
            if _is_scalar(attr_value):
                continue
            if attr_name in special_directives:
                attr_id = self.add_node(_create_list(len(attr_value)))
                for child_idx, child in enumerate(attr_value):
                    self.g.edge(f'{attr_id}:e{child_idx}', child.accept(self))
            else:
                attr_id = self.visit_raw(attr_value)
            self.g.edge(f'{b_id}:{attr_name}', attr_id)

        return b_id

    def visit_task(self, v: rep.Task) -> str:
        t_id = self.add_node(_create_record('Task', *v._yield_non_default_representable_attributes()))

        for attr_name, attr_value in v._yield_non_default_representable_attributes():
            if _is_scalar(attr_value):
                continue
            if attr_name == 'loop_control':
                attr_id = attr_value.accept(self)
            else:
                attr_id = self.visit_raw(attr_value)
            self.g.edge(f'{t_id}:{attr_name}', attr_id)

        return t_id

    def visit_handler(self, v: rep.Handler) -> str:
        t_id = self.add_node(_create_record('Handler', *v._yield_non_default_representable_attributes()))

        for attr_name, attr_value in v._yield_non_default_representable_attributes():
            if _is_scalar(attr_value):
                continue
            if attr_name == 'loop_control':
                attr_id = attr_value.accept(self)
            else:
                attr_id = self.visit_raw(attr_value)
            self.g.edge(f'{t_id}:{attr_name}', attr_id)

        return t_id

    def visit_loop_control(self, v: rep.LoopControl) -> str:
        lc_id = self.add_node(_create_record('LoopControl', *v._yield_non_default_representable_attributes()))

        for attr_name, attr_value in v._yield_non_default_representable_attributes():
            if _is_scalar(attr_value):
                continue

            self.g.edge(f'{lc_id}:{attr_name}', self.visit_raw(attr_value))

        return lc_id

    def visit_variable_file(self, v: rep.VariableFile) -> str:
        vf_id = self.add_node(_create_record('VariableFile', *v._yield_non_default_representable_attributes()))
        if v.variables:
            self.g.edge(f'{vf_id}:variables', self.visit_raw(v.variables))

        return vf_id

    def visit_broken_file(self, v: rep.BrokenFile) -> str:
        raise NotImplementedError('Should not reach here')

    def visit_broken_task(self, v: rep.BrokenTask) -> str:
        raise NotImplementedError('Should not reach here')


    def visit_platform(self, v: rep.Platform) -> str:
        return self.add_node(_create_record('Platform', *v._yield_non_default_representable_attributes()))

    def visit_role_requirement(self, v: rep.RoleRequirement) -> str:
        rr_id = self.add_node(_create_record('RoleRequirement', *v._yield_non_default_representable_attributes()))

        for attr_name, attr_value in v._yield_non_default_representable_attributes():
            if _is_scalar(attr_value):
                continue
            if attr_name == 'source_info':
                attr_id = attr_value.accept(self)
            else:
                attr_id = self.visit_raw(attr_value)
            self.g.edge(f'{rr_id}:{attr_name}', attr_id)

        return rr_id

    def visit_role_source_info(self, v: rep.RoleSourceInfo) -> str:
        return self.add_node(_create_record('RoleSourceInfo', *v._yield_non_default_representable_attributes()))

    def visit_vars_prompt(self, v: rep.VarsPrompt) -> str:
        vp_id = self.add_node(_create_record('VarsPrompt', *v._yield_non_default_representable_attributes()))

        for attr_name, attr_value in v._yield_non_default_representable_attributes():
            if _is_scalar(attr_value):
                continue

            self.g.edge(f'{vp_id}:{attr_name}', self.visit_raw(attr_value))

        return vp_id


def export_dot(model_root: rep.StructuralModel | rep.MultiStructuralModel) -> gv.Digraph:
    vis = VisualizationVisitor()
    model_root.accept(vis)
    return vis.full_graph
