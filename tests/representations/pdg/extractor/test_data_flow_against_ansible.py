"""Tests which test the inferred data flow against Ansible's behaviour."""

from __future__ import annotations

from typing import cast

import json
import tempfile
import subprocess
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PosixPath

import jinja2
import pytest
import yaml
try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper  # type: ignore[misc]
from hypothesis import assume, given, example, Phase, settings, strategies as st

from scansible.representations.pdg.extractor import extract_pdg
from scansible.representations.pdg.extractor.var_context import ScopeLevel
from scansible.representations.pdg.extractor.templates import TemplateExpressionAST
from scansible.representations.pdg import representation as rep
from scansible.representations.pdg.io.neo4j import dump_graph


_considered_scopes = [
    ScopeLevel.TASK_VARS,
    ScopeLevel.BLOCK_VARS,
    ScopeLevel.INCLUDE_VARS,
    ScopeLevel.SET_FACTS_REGISTERED,
    ScopeLevel.INCLUDE_PARAMS,
]
_considered_init_scopes = [
    ScopeLevel.ROLE_DEFAULTS,
    ScopeLevel.ROLE_VARS,
]
_ansible_scopes = st.sampled_from(_considered_scopes)
_ansible_init_scopes = st.sampled_from(_considered_init_scopes)
_ansible_var_names = st.sampled_from(['a', 'b', 'c'])  # Only allowing a limited number here because we WANT overlaps, that's the whole point
_ansible_file_names = st.text(alphabet='abcdef', min_size=1)

PlaybookFile = tuple[Path, str]
Dataflow = list[str]


class Block:
    content: list[dict[str, object]]
    var_deps: dict[str, set[str]]

    @property
    def all_var_deps(self) -> dict[str, set[str]]:
        return self._all_var_deps(0)

    def _all_var_deps(self, level: int) -> dict[str, set[str]]:
        print(f'{level} {self.block_name}: {self.var_deps}')
        if self.parent is None:
            return self.var_deps
        return {**self.parent._all_var_deps(level+1), **self.var_deps}

    def __init__(self, name: str, parent: Block | None = None) -> None:
        self.block_name = name
        self.parent = parent
        self.content = []
        self.var_deps = {}

    def depends_on(self, name: str, dep_name: str | set[str], real_dep_name: str | None = None) -> bool:
        """Does name depend on dep_name?"""
        if isinstance(dep_name, str):
            real_dep_name = dep_name
            dep_name = {dep_name}

        if name not in self.all_var_deps:
            return False

        if real_dep_name in self.all_var_deps[name]:
            return True

        if dep_name & self.all_var_deps[name]:
            # There's recursion somewhere in the chain. This may happen if a
            # variable has been defined through `set_fact` or other high-precedence
            # mechanisms, which we are not aware of here. It should never lead
            # to a problem at runtime, since the depended-on variable is shadowed
            # by a higher precedence one, but it would lead to unbounded recursion
            # in this function. There might be another cyclic dependency further
            # down, so over-approximate.
            return True

        dep_name |= self.all_var_deps[name]

        return any(
                self.depends_on(trans_name, dep_name, real_dep_name)
                for trans_name in self.all_var_deps[name])


class CodeGen:

    def __init__(self, draw: st.DrawFn) -> None:
        self.last_val = 0
        self.last_prefix = 0
        self._init_vars_printed: set[str] = set()
        self._used_variables: set[str] = set()

        defaults_block = Block('defaults')
        defaults_block.content.append({})
        var_block = Block('vars', defaults_block)
        var_block.content.append({})
        role_block = Block('role root', var_block)

        self._files: dict[Path, list[dict[str, object]]] = {
                Path('tasks/main.yml'): role_block.content,
                Path('vars/main.yml'): var_block.content,
                Path('defaults/main.yml'): defaults_block.content,
        }

        self._block_stack = [defaults_block, var_block, role_block]
        self._include_vars_stack: list[Block] = []
        self._included_file_names: set[str] = set()
        self._included_tasks_names: set[str] = set()
        self._set_facts_vars: set[str] = set()
        self.draw = draw

    @property
    def curr_block(self) -> Block:
        return self._block_stack[-1]

    @property
    def parent_block(self) -> Block:
        return self._block_stack[-2]

    @property
    def vars_block(self) -> Block:
        return self._block_stack[1]

    @property
    def defaults_block(self) -> Block:
        return self._block_stack[0]

    @property
    def role_block(self) -> Block:
        return self._block_stack[2]

    @property
    def is_in_local_block(self) -> bool:
        return len(self._block_stack) > 3

    @property
    def is_in_nested_local_block(self) -> bool:
        return len(self._block_stack) > 4

    def add_var_to_scope(self, scope_level: ScopeLevel) -> None:
        adders = {
            ScopeLevel.ROLE_DEFAULTS: self._add_default,
            ScopeLevel.ROLE_VARS: self._add_role_var,
            ScopeLevel.BLOCK_VARS: self._add_block_local,
            ScopeLevel.TASK_VARS: self._add_task_local,
            ScopeLevel.INCLUDE_VARS: self._add_include,
            ScopeLevel.SET_FACTS_REGISTERED: self._add_set_fact,
            ScopeLevel.INCLUDE_PARAMS: self._add_include_tasks,
        }

        adders[scope_level]()

    def _add_default(self) -> None:
        name = self.draw(_ansible_var_names)
        val = self._draw_value(name, self.defaults_block, False)
        self.defaults_block.content[0][name] = val
        self._add_init_print(name)
        self._used_variables.add(name)

    def _add_role_var(self) -> None:
        name = self.draw(_ansible_var_names)
        val = self._draw_value(name, self.vars_block, False)
        self.vars_block.content[0][name] = val
        self._add_init_print(name)
        self._used_variables.add(name)

    def _add_block_local(self) -> None:
        if not self.is_in_local_block or self.draw(st.booleans()):
            # Need to push for a local
            self._push_local_scope()
        elif self.is_in_nested_local_block and self.draw(st.booleans()):
            # Descend again
            self._pop_local_scope()

        name = self.draw(_ansible_var_names)
        val = self._draw_value(name)
        block_vars = cast(
                dict[str, object],
                self.parent_block.content[-1].setdefault('vars', {}))
        block_vars[name] = val
        self._add_print(name)
        self._used_variables.add(name)

        # Vars in nested blocks don't override outer blocks, so make sure not
        # to override dependencies to prevent accidental recursive definitions
        for parent in self._block_stack[2:-1]:
            if name in parent.var_deps:
                del self.curr_block.var_deps[name]
                break

    def _add_task_local(self) -> None:
        # HACK: _draw_value modifies the block to set some information about
        # its variables, so we create a fake block to represent the task's locals.
        fake_block = Block('fake task', self.curr_block)
        name = self.draw(_ansible_var_names)
        val = self._draw_value(name, fake_block)
        self._add_print(name)
        # Adding to the printer we added in the previous line
        task_vars = cast(
                dict[str, object],
                self.curr_block.content[-1].setdefault('vars', {}))
        task_vars[name] = val
        self._used_variables.add(name)

    def _add_include(self) -> None:
        file_name = self.draw(_ansible_file_names.filter(
                lambda n: n not in self._included_file_names))
        var_names = self.draw(st.lists(_ansible_var_names, unique=True, min_size=1))
        file_path = Path('vars', file_name + '.yml')
        file_content: dict[str, str] = {}
        self._files[file_path] = [cast(dict[str, object], file_content)]

        incl_task: dict[str, object] = {
            'include_vars': str(file_path)
        }
        self.curr_block.content.append(incl_task)
        if self._include_vars_stack:
            incl_block = Block('incl_vars', self._include_vars_stack[-1])
        else:
            incl_block = Block('incl_vars')
        self._include_vars_stack.append(incl_block)

        for var_name in var_names:
            # Only allow definitions in terms of other included variables,
            # because the awful precedence rules make it easy to accidentally
            # create recursive definitions elsewhere
            val = self._draw_value(var_name, incl_block)
            file_content[var_name] = val
            self._add_print(var_name)
            self._used_variables.add(var_name)

        self._included_file_names.add(file_name)

    def _add_set_fact(self) -> None:
        name = self.draw(_ansible_var_names)
        # Not using _draw_value here, because we can just reuse the same variable,
        # since the expression will be evaluated eagerly before defining the new
        # var.
        # TODO: Set vars on this task
        should_reuse = bool(self.curr_block.all_var_deps) and self.draw(st.booleans())
        if should_reuse:
            reuse_var = self.draw(st.sampled_from(sorted(self.curr_block.all_var_deps.keys())))
            val = f'{{{{ {reuse_var} }}}}'
        else:
            val = self._next_value

        task: dict[str, object] = {
            'set_fact': {
                name: val
            }
        }
        self.curr_block.content.append(task)
        self._add_print(name)
        self._set_facts_vars.add(name)
        self._used_variables.add(name)

    def _add_include_tasks(self) -> None:
        file_name = self.draw(_ansible_file_names.filter(
                lambda n: n not in self._included_tasks_names))
        block = Block('incl_tasks', self.curr_block)
        var_names = self.draw(st.lists(_ansible_var_names, unique=True, min_size=1))
        file_path = Path('tasks', file_name + '.yml')
        incl_task: dict[str, object] = {
            'name': f'Include {file_name}',
            'include_tasks': str(file_path),
            'vars': {}
        }
        self._files[file_path] = block.content

        for var_name in var_names:
            var_val = self._draw_value(var_name, block)
            incl_task['vars'][var_name] = var_val  # type: ignore[index]
            self._add_print(var_name, block)
            self._used_variables.add(var_name)
        self.curr_block.content.append(incl_task)
        self._block_stack.append(block)
        self._included_tasks_names.add(file_name)

    def _push_local_scope(self) -> None:
        new_block = Block('block', self.curr_block)
        self.curr_block.content.append({'block': new_block.content})
        self._block_stack.append(new_block)

    def _pop_local_scope(self) -> None:
        self._block_stack.pop()

    @property
    def _next_value(self) -> str:
        self.last_val += 1
        return str(self.last_val - 1)

    def _draw_value(self, name: str, from_block: Block | None = None, def_at_runtime: bool = True) -> str:
        if from_block is None:
            from_block = self.curr_block

        reusable_vars = [
                var_name for var_name in from_block.all_var_deps.keys()
                if var_name != name]
        if not def_at_runtime:
            # Role vars or role defaults, need to check the chain to prevent
            # recursive definitions
            reusable_vars = [
                    var_name for var_name in reusable_vars
                    if not from_block.depends_on(var_name, name)]
        else:
            # Defined at runtime, couple of edge cases to consider
            new_rvs = []
            for reusable_var in reusable_vars:
                if reusable_var in self._set_facts_vars:
                    # Constant variable, no recursive definition possible, so
                    # definitely reusable
                    new_rvs.append(reusable_var)
                    continue
                if self._include_vars_stack and self._include_vars_stack[-1].depends_on(reusable_var, name):
                    # Included vars take precedence, and the proposed var is included
                    # and already depends on the same name -> Would be a recursive definition
                    continue
                if not from_block.depends_on(reusable_var, name):
                    new_rvs.append(reusable_var)
            reusable_vars = new_rvs

        # No variables to reuse, or we shouldn't reuse variables now
        if not reusable_vars or not self.draw(st.booleans()):
            from_block.var_deps[name] = set()
            return self._next_value

        reuse_var = self.draw(st.sampled_from(reusable_vars))
        from_block.var_deps[name] = {reuse_var}
        return f'{{{{ {reuse_var} }}}}'

    def _add_print(self, name: str, to_stack: Block | None = None, prepend: bool = False) -> None:
        if to_stack is None:
            to_stack = self.curr_block

        task: dict[str, object] = {
            'debug': {
                'msg': f'{self.last_prefix} is {{{{ {name} }}}}'
            }
        }
        self.last_prefix += 1
        if prepend:
            to_stack.content.insert(0, task)
        else:
            to_stack.content.append(task)

    def _add_init_print(self, name: str) -> None:
        if name not in self._init_vars_printed:
            self._add_print(name, self.role_block)
            self._init_vars_printed.add(name)

    @property
    def files(self) -> list[PlaybookFile]:
        # Make sure to print the final value of the variables, for locally scoped
        # ones.
        for v in self._used_variables:
            self.role_block.content.append({
                'name': f'{v} is defined?',
                'debug': {
                    'msg': f'{{{{ {v} | default(false) }}}}'
                }
            })

        files = []
        for fp, content in self._files.items():
            if fp.parent.name != 'tasks' and content:
                content = content[0]  # type: ignore[assignment]
            if not content:
                continue
            files.append((fp, yaml.dump(content, Dumper=Dumper)))

        return files



@st.composite
def ansible_playbooks(draw: st.DrawFn) -> list[PlaybookFile]:
    init_scopes = draw(st.lists(_ansible_init_scopes))
    scopes = draw(st.lists(_ansible_scopes))
    assume(bool(init_scopes + scopes))

    code_gen = CodeGen(draw)
    for init_scope in init_scopes:
        code_gen.add_var_to_scope(init_scope)
    for scope in scopes:
        try:
            code_gen.add_var_to_scope(scope)
        except RecursionError:
            raise RuntimeError('recursion error') from None

    return code_gen.files


@pytest.mark.slow
@given(ansible_playbooks())
@settings(deadline=None, max_examples=100)
def test_inferred_dataflow_matches_actual(playbooks: list[PlaybookFile]) -> None:  # type: ignore[misc]
    with _setup_env(playbooks) as playbook_dir:
        try:
            graph = _parse_graph(playbook_dir / 'roles' / 'test')
        except RecursionError as e:
            assume(False)
            return

        try:
            inferred_dataflow = _infer_dataflow(graph)
            actual_dataflow = _observe_dataflow(playbook_dir)

            assert inferred_dataflow == actual_dataflow
        except:
            print(playbooks)
            print(dump_graph(graph))
            raise


@contextmanager
def _setup_env(playbooks: list[PlaybookFile]) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmpdir_s:
        tmpdir = Path(tmpdir_s)
        role_dir = tmpdir / 'roles' / 'test'
        for pb in playbooks:
            (role_dir / pb[0]).parent.mkdir(exist_ok=True, parents=True)
            (role_dir / pb[0]).write_text(pb[1])

        (tmpdir / 'pb.yml').write_text('''
- gather_facts: no
  connection: local
  hosts: localhost
  tasks:
    - include_role:
        name: test''')

        yield Path(tmpdir)


def _parse_graph(playbook_dir: Path) -> rep.Graph:
    return extract_pdg(playbook_dir.resolve(), 'test', 'test', [Path()]).graph


def _infer_dataflow(graph: rep.Graph) -> Dataflow:
    printers = _yield_debug_tasks(graph)
    # TODO: We should check the order of printing as well.
    return sorted([_get_expected_output(printer, graph) for printer in printers])


def _yield_debug_tasks(graph: rep.Graph) -> Iterable[rep.Task]:
    for node in graph:
        if not isinstance(node, rep.Task):
            continue
        if node.action == 'debug':
            yield node


def _get_expected_output(printer: rep.Task, graph: rep.Graph) -> str:
    expr = _get_printed_expr(printer, graph)
    if printer.name and printer.name.endswith('is defined?'):
        use_node = list(_find_predecessors(graph, expr, rep.USE))[0]
        # Defined, get the value
        if isinstance(use_node, rep.IntermediateValue):
            return _resolve_iv_to_value(graph, use_node)
        if isinstance(use_node, rep.Variable):
            val = _resolve_var_to_value(graph, use_node)
            if val is None:
                # Not defined any longer, prints "false"
                return 'False'
            return val

    return _resolve_expr_to_value(graph, expr)


def _get_printed_expr(printer: rep.Task, graph: rep.Graph) -> rep.Expression:
    message_iv = list(_find_predecessors(graph, printer, rep.Keyword(keyword='args.msg')))
    assert message_iv, 'No expression?!'
    assert len(message_iv) == 1, 'Multiple expressions?!'

    # IV should've been produced by an expression
    expr = next(_find_predecessors(graph, message_iv[0], rep.DEF))
    assert isinstance(expr, rep.Expression), 'Wrong node type?!'
    return expr


def _find_predecessors(g: rep.Graph, n: rep.Node, edata: rep.Edge) -> Iterator[rep.Node]:
    for e in g.edges():
        if not e[1] == n:
            continue
        if g[e[0]][n].get(0)['type'] == edata:  # type: ignore[index]
            yield e[0]


def _resolve_expr_to_value(g: rep.Graph, expr: rep.Expression) -> str:
    # Should only use one data node
    used_data = next(_find_predecessors(g, expr, rep.USE))
    if isinstance(used_data, rep.Literal):
        data = used_data.value
    elif isinstance(used_data, rep.IntermediateValue):
        data = _resolve_iv_to_value(g, used_data)
    elif isinstance(used_data, rep.Variable):
        data = _resolve_var_to_value(g, used_data)
        assert data is not None
    else:
        raise ValueError(f'invalid USE node: {type(used_data)} {used_data}')

    templ = jinja2.Template(expr.expr)
    templ_ast = TemplateExpressionAST.parse(expr.expr)
    assert templ_ast is not None
    var_names = templ_ast.referenced_variables
    var_name = next(iter(var_names))
    return templ.render(**{var_name: data})


def _resolve_iv_to_value(g: rep.Graph, iv: rep.IntermediateValue) -> str:
    def_node = next(_find_predecessors(g, iv, rep.DEF))
    assert isinstance(def_node, rep.Expression), f'unexpected DEF node: {def_node}'
    return _resolve_expr_to_value(g, def_node)


def _resolve_var_to_value(g: rep.Graph, v: rep.Variable) -> str | None:
    def_nodes = list(_find_predecessors(g, v, rep.DEF))
    if not def_nodes:
        return None
    assert len(def_nodes) == 1, 'Multiple defs should not happen here!'
    def_node = def_nodes[0]
    assert isinstance(def_node, (rep.IntermediateValue, rep.Literal)), f'unexpected DEF node: {def_node}'
    if isinstance(def_node, rep.IntermediateValue):
        return _resolve_iv_to_value(g, def_node)
    return str(def_node.value)


def _observe_dataflow(playbook_dir: Path) -> Dataflow:
    proc = subprocess.run(
            ['/usr/local/bin/ansible-playbook', 'pb.yml', '--connection=local'],
            capture_output=True, text=True,
            env={'ANSIBLE_STDOUT_CALLBACK': 'json'}, cwd=playbook_dir)
    assert not proc.returncode, proc.stderr
    out = json.loads(proc.stdout)
    result = []
    from pprint import pprint
    pprint(out['plays'][0]['tasks'])
    for t in out['plays'][0]['tasks']:
        task_res = t['hosts']['localhost']
        if task_res['action'] != 'debug':
            continue
        result.append(str(task_res['msg']))

    return sorted(result)
