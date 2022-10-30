"""Extraction logic for structural model."""
from __future__ import annotations

from typing import Any, Callable, Literal, TypeVar, overload, TYPE_CHECKING

from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from pathlib import Path

from . import representation as rep, ansible_types as ans, loaders
from .helpers import ProjectPath, parse_file, validate_ansible_object, capture_output, find_all_files, find_file, FatalError, prevent_undesired_operations, convert_ansible_values


def extract_role_metadata_file(path: ProjectPath) -> rep.MetaFile:
    """Extract the structural representation of a metadata file."""

    ds, raw_ds = loaders.load_role_metadata(path)

    ds_platforms: list[dict[str, Any]] = ds['galaxy_info']['platforms']  # type: ignore
    ds_dependencies: list[dict[str, Any]] = ds['dependencies']  # type: ignore

    platforms = [rep.Platform(p['name'], v) for p in ds_platforms for v in p['versions']]
    dependencies = [rep.Dependency(role=dep['name'], when=dep['when']) for dep in ds_dependencies]

    metablock = rep.MetaBlock(platforms=platforms, dependencies=dependencies, raw=raw_ds)
    metafile = rep.MetaFile(metablock=metablock, file_path=path.relative)
    metablock.parent = metafile
    return metafile


def extract_variable_file(path: ProjectPath) -> rep.VariableFile:
    ds, raw_ds = loaders.load_variable_file(path)

    variables = extract_list_of_variables(ds)
    varfile = rep.VariableFile(file_path=path.relative, variables=variables)
    for v in variables:
        v.parent = varfile
    return varfile


def extract_list_of_variables(ds: dict[str, ans.AnsibleValue]) -> list[rep.Variable]:
    return [rep.Variable(name=k, value=convert_ansible_values(v)) for k, v in ds.items()]


def extract_tasks_file(path: ProjectPath, handlers: bool = False) -> rep.TaskFile:
    ds, raw_ds = loaders.load_tasks_file(path)

    content = extract_list_of_tasks_or_blocks(ds, handlers)  # type: ignore[call-overload]
    tf = rep.TaskFile(file_path=path.relative, tasks=content)
    for child in content:
        child.parent = tf
    return tf

@overload
def extract_list_of_tasks_or_blocks(ds: list[dict[str, ans.AnsibleValue]], handlers: Literal[True]) -> list[rep.Handler | rep.Block]: ...
@overload
def extract_list_of_tasks_or_blocks(ds: list[dict[str, ans.AnsibleValue]], handlers: Literal[False] = ...) -> list[rep.Task | rep.Block]: ...

def extract_list_of_tasks_or_blocks(ds: list[dict[str, ans.AnsibleValue]], handlers: Literal[True, False] = False) -> list[rep.Task | rep.Block] | list[rep.Handler | rep.Block]:
    content = []
    for inner_ds in ds:
        content.append(extract_task_or_block(inner_ds, handlers))
    return content  # type: ignore[return-value]


@overload
def extract_task_or_block(ds: dict[str, ans.AnsibleValue], handlers: Literal[False]) -> rep.Task | rep.Block: ...
@overload
def extract_task_or_block(ds: dict[str, ans.AnsibleValue], handlers: Literal[True]) -> rep.Handler | rep.Block: ...

def extract_task_or_block(ds: dict[str, ans.AnsibleValue], handlers: Literal[True, False] = False) -> rep.Handler | rep.Task | rep.Block:
    if ans.Block.is_block(ds):
        return extract_block(ds, handlers)

    return extract_handler(ds) if handlers else extract_task(ds)


def extract_block(ds: dict[str, ans.AnsibleValue], handlers: Literal[True, False] = False) -> rep.Block:
    raw_block, raw_ds = loaders.load_block(ds)

    children_block = extract_list_of_tasks_or_blocks(raw_block.block, handlers=handlers)
    children_rescue = extract_list_of_tasks_or_blocks(raw_block.rescue, handlers=handlers)
    children_always = extract_list_of_tasks_or_blocks(raw_block.always, handlers=handlers)

    block = rep.Block(
            name=raw_block.name,
            block=children_block,
            rescue=children_rescue,
            always=children_always,
            vars=extract_list_of_variables(raw_block.vars),
            raw=raw_ds
    )

    for child in children_block + children_rescue + children_always:
        child.parent = block

    return block


def _extract_loop_control(lc: ans.LoopControl | None) -> rep.LoopControl | None:
    if lc is None:
        return None

    validate_ansible_object(lc)
    return rep.LoopControl(
        loop_var=lc.loop_var,
        index_var=lc.index_var,
        label=lc.label,
        pause=lc.pause,
        extended=lc.extended,
    )


def extract_task(ds: dict[str, ans.AnsibleValue]) -> rep.Task:
    raw_task, raw_ds = loaders.load_task(ds, False)

    return rep.Task(
        name=raw_task.name,
        action=raw_task.action,
        args=convert_ansible_values(raw_task.args),
        when=raw_task.when,
        loop=raw_task.loop,
        loop_with=raw_task.loop_with,
        loop_control=_extract_loop_control(raw_task.loop_control),
        vars=extract_list_of_variables(raw_task.vars),
        register=raw_task.register,
        raw=raw_ds,
    )


def extract_handler(ds: dict[str, ans.AnsibleValue]) -> rep.Handler:
    raw_handler, raw_ds = loaders.load_task(ds, True)

    return rep.Handler(
        name=raw_handler.name,
        action=raw_handler.action,
        args=convert_ansible_values(raw_handler.args),
        when=raw_handler.when,
        loop=raw_handler.loop,
        loop_with=raw_handler.loop_with,
        loop_control=_extract_loop_control(raw_handler.loop_control),
        vars=extract_list_of_variables(raw_handler.vars),
        listen=raw_handler.listen,
        register=raw_handler.register,
        raw=raw_ds,
    )


def extract_play(ds: dict[str, ans.AnsibleValue]) -> rep.Play:
    raw_play, raw_ds = loaders.load_play(ds)

    play = rep.Play(
        name=raw_play.name,
        hosts=raw_play.hosts,
        tasks=extract_list_of_tasks_or_blocks(raw_play.tasks, handlers=False),
        vars=extract_list_of_variables(raw_play.vars),
        raw=raw_ds
    )
    for child in play.tasks:
        child.parent = play
    return play


def extract_playbook(path: Path, id: str, version: str) -> rep.StructuralModel:
    """
    Extract a structural model from a playbook.

    :param      path:     The path to the playbook.
    :type       path:     Path
    :param      id:       The identifier for the playbook.
    :type       id:       str
    :param      version:  The version of the playbook.
    :type       version:  str

    :returns:   Extracted structural model.
    :rtype:     StructuralModel
    """

    pb_path = ProjectPath.from_root(path)

    with capture_output() as output, prevent_undesired_operations():
        ds, raw_ds = loaders.load_playbook(pb_path)

        # Parse the plays in the playbook
        plays = [extract_play(play_ds) for play_ds in ds]

    pb = rep.Playbook(plays=plays, raw=ds)
    for play in plays:
        play.parent = pb
    return rep.StructuralModel(root=pb, path=path, id=id, version=version, logs=output.getvalue())


def extract_role(path: Path, id: str, version: str, extract_all: bool = False) -> rep.StructuralModel:
    """
    Extract a structural model from a role.

    :param      path:         The path to the role.
    :type       path:         Path
    :param      id:           The identifier for the role.
    :type       id:           str
    :param      version:      The version of the role.
    :type       version:      str
    :param      extract_all:  Whether to extract all available files, or just
                              the main files. Defaults to `False`. Additional
                              files can still be extracted using
                              `extract_task_file` or `extract_variable_file`.
    :type       extract_all:  bool

    :returns:   Extracted structural model.
    :rtype:     StructuralModel
    """

    role_path = ProjectPath.from_root(path)

    # Extract all constituents
    task_files: dict[str, rep.TaskFile] = {}
    handler_files: dict[str, rep.TaskFile] = {}
    vars_files: dict[str, rep.VariableFile] = {}
    defaults_files: dict[str, rep.VariableFile] = {}
    meta_files: dict[str, rep.MetaFile] = {}
    broken_files: list[rep.BrokenFile] = []

    with capture_output() as output, prevent_undesired_operations():
        meta_file_path = find_file(role_path, 'meta/main')
        _safe_extract(extract_role_metadata_file, meta_file_path, meta_files, broken_files)
        meta_file = next(iter(meta_files.values())) if meta_files else None

        if extract_all:
            get_dir = partial(ProjectPath, role_path.absolute)

            _safe_extract_all(partial(extract_tasks_file, handlers=False), get_dir('tasks'), task_files, broken_files)
            _safe_extract_all(partial(extract_tasks_file, handlers=True), get_dir('handlers'), handler_files, broken_files)
            _safe_extract_all(extract_variable_file, get_dir('vars'), vars_files, broken_files)
            _safe_extract_all(extract_variable_file, get_dir('defaults'), defaults_files, broken_files)
        else:
            def get_main_path(dirname: str) -> ProjectPath | None:
                return find_file(role_path.join(dirname), 'main')

            _safe_extract(partial(extract_tasks_file, handlers=False), get_main_path('tasks'), task_files, broken_files)
            _safe_extract(partial(extract_tasks_file, handlers=True), get_main_path('handlers'), handler_files, broken_files)
            _safe_extract(extract_variable_file, get_main_path('defaults'), defaults_files, broken_files)
            _safe_extract(extract_variable_file, get_main_path('vars'), vars_files, broken_files)

    role = rep.Role(
        task_files=task_files,
        handler_files=handler_files,
        role_var_files=vars_files,
        default_var_files=defaults_files,
        meta_file=meta_file,
        broken_files=broken_files,
    )

    return rep.StructuralModel(
        root=role,
        path=path,
        id=id,
        version=version,
        logs=output.getvalue()
    )


ExtractedFileType = TypeVar('ExtractedFileType')


def _safe_extract(extractor: Callable[[ProjectPath], ExtractedFileType], file_path: ProjectPath | None, file_dict: dict[str, ExtractedFileType], broken_files: list[rep.BrokenFile]) -> None:
    if file_path is None:
        return

    try:
        extracted_file = extractor(file_path)
        file_dict['/'.join(file_path.relative.parts[1:])] = extracted_file
    except (ans.AnsibleError, loaders.LoadError) as e:
        broken_files.append(rep.BrokenFile(path=file_path.relative, reason=str(e)))


def _safe_extract_all(extractor: Callable[[ProjectPath], ExtractedFileType], dir_path: ProjectPath, file_dict: dict[str, ExtractedFileType], broken_files: list[rep.BrokenFile]) -> None:
    if not dir_path.absolute.is_dir():
        return

    for child_path in find_all_files(dir_path):
        _safe_extract(extractor, child_path, file_dict, broken_files)
