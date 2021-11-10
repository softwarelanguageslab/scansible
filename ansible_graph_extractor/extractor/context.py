from __future__ import annotations

from pydantic import BaseModel

from voyager.models.structural.role import (
        HandlerFile, DefaultVarFile, RoleVarFile, TaskFile, Role)
from voyager.models.structural.abstract import ContainerFile

from ..models.graph import Graph
from ..models import nodes as n
from .var_context import VarContext


class Files(BaseModel):
    task_files: dict[str, TaskFile] = {}
    handler_files: dict[str, HandlerFile] = {}
    var_files: dict[str, RoleVarFile] = {}
    defaults_files: dict[str, DefaultVarFile] = {}

    main_task_file: TaskFile | None = None
    main_handler_file: HandlerFile | None = None
    main_var_file: RoleVarFile | None = None
    main_defaults_file: DefaultVarFile | None = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def categorise(cls, role: Role) -> Files:
        files = Files()

        for tf in role.task_files:
            name = get_file_name(tf)
            if name == 'main':
                assert files.main_task_file is None
                files.main_task_file = tf

            assert name not in files.task_files
            files.task_files[name] = tf

        for hf in role.handler_files:
            name = get_file_name(hf)
            if name == 'main':
                assert files.main_handler_file is None
                files.main_handler_file = hf

            assert name not in files.handler_files
            files.handler_files[name] = hf

        for vf in role.role_var_files:
            name = get_file_name(vf)
            if name == 'main':
                assert files.main_var_file is None
                files.main_var_file = vf

            assert name not in files.var_files
            files.var_files[name] = vf

        for df in role.default_var_files:
            name = get_file_name(df)
            if name == 'main':
                assert files.main_defaults_file is None
                files.main_defaults_file = df

            assert name not in files.defaults_files
            files.defaults_files[name] = df

        return files


class ExtractionContext():
    vars: VarContext
    graph: Graph
    files: Files
    _next_id: int
    _next_iv_id: int

    def __init__(self, graph: Graph, files: Files) -> None:
        self.vars = VarContext(self)
        self.graph = graph
        self.files = files
        self._next_id = 0
        self._next_iv_id = 0

    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def next_iv_id(self) -> int:
        self._next_iv_id += 1
        return self._next_iv_id - 1


def get_file_name(f: ContainerFile | str) -> str:  # type: ignore[type-arg]
    if not isinstance(f, str):
        return get_file_name(f.file_name)
    parent_dir, *name_no_dir_parts = f.split('/')
    if name_no_dir_parts and parent_dir in ('tasks', 'handlers', 'vars', 'defaults'):
        name_no_dir = '/'.join(name_no_dir_parts)
    else:
        name_no_dir = f

    name_no_ext = '.'.join(name_no_dir.split('.')[:-1])
    return name_no_ext

class ExtractionResult(BaseModel):
    added_control_nodes: list[n.ControlNode]

class TaskExtractionResult(ExtractionResult):
    next_predecessors: list[n.ControlNode]
