"""Extraction logic for structural model."""
from __future__ import annotations

from typing import Any, Callable, Literal, TypeVar, overload, TYPE_CHECKING

from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from pathlib import Path

import ansible
import ansible.playbook
import ansible.playbook.task
import ansible.playbook.handler_task_include
import ansible.playbook.task_include
import ansible.playbook.block
import ansible.playbook.handler
import ansible.playbook.play
import ansible.parsing.dataloader
import ansible.parsing.mod_args

if TYPE_CHECKING:
    # This alias doesn't exist outside of the stub files
    from ansible.playbook.base import Value as AnsibleValue

from . import representation as rep
from .helpers import ProjectPath, parse_file, validate_ansible_object, capture_output, find_all_files, find_file, FatalError, prevent_undesired_operations


# Patch the ModuleArgsParser so that it doesn't verify whether the action exist.
# Otherwise it'll complain on non-builtin actions
old_mod_args_parse = ansible.parsing.mod_args.ModuleArgsParser.parse
ansible.parsing.mod_args.ModuleArgsParser.parse = lambda self, skip_action_validation=False: old_mod_args_parse(self, skip_action_validation=True)  # type: ignore[assignment]


def extract_role_metadata_file(path: ProjectPath) -> rep.MetaFile:
    """Extract the structural representation of a metadata file."""

    ds = parse_file(path)
    # Need to do the validation ourselves because role metadata parsing is
    # heavily under-validated in Ansible.
    assert ds, 'Empty role metadata'
    assert isinstance(ds, dict), 'Metadata file does not contain a dictionary'

    platforms = _extract_meta_platforms(ds)
    dependencies = _extract_meta_dependencies(ds)

    metablock = rep.MetaBlock(platforms=platforms, dependencies=dependencies, raw=ds)
    metafile = rep.MetaFile(metablock=metablock, file_path=path.relative)
    metablock.parent = metafile
    return metafile


def _extract_meta_platforms(meta: dict[str, AnsibleValue]) -> list[rep.Platform]:
    galaxy_info: Any = meta.get('galaxy_info', {})
    assert isinstance(galaxy_info, dict), f'galaxy_info expected to be a dictionary, got {galaxy_info!r}'
    raw_platforms: Any = galaxy_info.get('platforms', [])
    assert isinstance(raw_platforms, (tuple, list)), f'platforms expected to be a list, got {raw_platforms!r}'

    platforms: list[rep.Platform] = []
    for p in raw_platforms:
        assert (
                isinstance(p, dict)
                and isinstance(p.get('name'), str)
                and isinstance(p.get('versions'), list)
                and all(isinstance(v, (str, int, float)) for v in p['versions'])
            ), f'Malformed platform, got {p!r}'

        platforms.extend(rep.Platform(p['name'], v) for v in p['versions'])

    return platforms


def _extract_meta_dependencies(meta: dict[str, AnsibleValue]) -> list[rep.Dependency]:
    raw_deps: Any = meta.get('dependencies', [])
    assert isinstance(raw_deps, list), f'Expected role dependencies to be a list, got {raw_deps}'

    deps: list[rep.Dependency] = []
    for ds in raw_deps:
        assert isinstance(ds, (str, dict)), f'Expected role dependency to be a string or dict, got {ds}'
        if isinstance(ds, str):
            deps.append(rep.Dependency(role=ds, when=[]))
            continue

        assert not (ds.keys() - {'name', 'role', 'when'}), f'Unsupported keys in role dependency: {ds}'
        assert ('name' in ds) != ('role' in ds), f'Both "name" and "role" are specified in role dependency: {ds}'
        name = ds.get('name', ds.get('role'))
        assert isinstance(name, str), f'Expected role name to be a string, got {name}'
        when = ds.get('when')
        assert when is None or isinstance(when, str) or (isinstance(when, list) and all(isinstance(cond, str) for cond in when)), f'Malformed dependency condition: {when}'
        if not when:
            when = []
        elif isinstance(when, str):
            when = [when]
        deps.append(rep.Dependency(role=name, when=when))

    return deps


def extract_variable_file(path: ProjectPath) -> rep.VariableFile:
    ds = parse_file(path)
    assert ds is None or isinstance(ds, dict), f'Expected variable file {path.relative} to contain a dictionary, got {type(ds)}'

    variables = extract_vars(ds) if ds is not None else []
    varfile = rep.VariableFile(file_path=path.relative, variables=variables)
    for v in variables:
        v.parent = varfile
    return varfile


def extract_vars(ds: dict[str, AnsibleValue]) -> list[rep.Variable]:
    return [rep.Variable(name=k, value=v) for k, v in ds.items()]


def extract_tasks_file(path: ProjectPath, handlers: bool = False) -> rep.TaskFile:
    ds = parse_file(path)
    assert ds is None or isinstance(ds, list), f'Expected task file {path.relative} to be a list, got {type(ds)}'

    content = extract_list_of_tasks_or_blocks(ds, handlers) if ds is not None else [] # type: ignore[call-overload]
    tf = rep.TaskFile(file_path=path.relative, tasks=content)
    for child in content:
        child.parent = tf
    return tf

@overload
def extract_list_of_tasks_or_blocks(ds: list[dict[str, AnsibleValue]], handlers: Literal[False]) -> list[rep.Task | rep.Block]: ...
@overload
def extract_list_of_tasks_or_blocks(ds: list[dict[str, AnsibleValue]], handlers: Literal[True]) -> list[rep.Handler]: ...

def extract_list_of_tasks_or_blocks(ds: list[dict[str, AnsibleValue]], handlers: bool = False) -> list[rep.Task | rep.Block] | list[rep.Handler]:
    content = []
    for inner_ds in ds:
        assert isinstance(inner_ds, dict) and all(isinstance(k, str) for k in inner_ds), 'Task list content must be a list of dictionaries'
        content.append(extract_task_or_block(inner_ds, handlers))  # type: ignore[call-overload]
    return content


@overload
def extract_task_or_block(ds: dict[str, AnsibleValue], handlers: Literal[False]) -> rep.Task | rep.Block: ...
@overload
def extract_task_or_block(ds: dict[str, AnsibleValue], handlers: Literal[True]) -> rep.Handler: ...

def extract_task_or_block(ds: dict[str, AnsibleValue], handlers: bool = False) -> rep.Handler | rep.Task | rep.Block:
    if ansible.playbook.block.Block.is_block(ds):
        if handlers:
            raise FatalError('Found a block in what is supposed to be a handler, TODO?')
        return extract_block(ds)

    return extract_handler(ds) if handlers else extract_task(ds)


class _PatchedBlock(ansible.playbook.block.Block):

    block: list[dict[str, AnsibleValue]]  # type: ignore[assignment]
    rescue: list[dict[str, AnsibleValue]]  # type: ignore[assignment]
    always: list[dict[str, AnsibleValue]]  # type: ignore[assignment]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # Remove the loaders from the block implementation, since they dispatch
        # to ansible.playbook.helpers.load_list_of_tasks, which does eager
        # loading of import_* tasks and inlines the imported roles/tasks into
        # the block. We don't want that to happen.
        self._load_block = None
        self._load_rescue = None
        self._load_always = None


# Workaround for error messages using the wrong class name.
_PatchedBlock.__name__ = 'Block'


def extract_block(ds: dict[str, AnsibleValue]) -> rep.Block:
    assert _PatchedBlock.is_block(ds), f'Not a block: {ds}'
    raw_block = _PatchedBlock(ds)
    raw_block.load_data(ds)
    validate_ansible_object(raw_block)

    children_block = extract_list_of_tasks_or_blocks(raw_block.block, handlers=False)
    children_rescue = extract_list_of_tasks_or_blocks(raw_block.rescue, handlers=False)
    children_always = extract_list_of_tasks_or_blocks(raw_block.always, handlers=False)

    block = rep.Block(
            name=raw_block.name,
            block=children_block,
            rescue=children_rescue,
            always=children_always,
            vars=extract_vars(raw_block.vars),
            raw=ds
    )

    for child in children_block + children_rescue + children_always:
        child.parent = block

    return block

@overload
def _extract_import_task(ds: dict[str, AnsibleValue], action: str, args: Any, handler: Literal[False] = ...) -> rep.Task: ...
@overload
def _extract_import_task(ds: dict[str, AnsibleValue], action: str, args: Any, handler: Literal[True]) -> rep.Handler: ...
def _extract_import_task(ds: dict[str, AnsibleValue], action: str, args: Any, handler: bool = False) -> rep.Task | rep.Handler:
    # Special-case all import/include tasks, like what's done in ansible.playbook.helpers.load_list_of_tasks
    if action in ansible.constants._ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES:
        raise FatalError('TODO: Import/include on a role')

    # Current Ansible version crashes when the old static key is used. Transform
    # it to modern syntax.
    if 'static' in ds:
        assert 'include' in ds, '"static" directive without "include" action'
        is_static = ds['static']
        if isinstance(is_static, str):
            assert is_static in ('yes', 'no'), f'Invalid boolean value for "static": {is_static}'
            is_static = (is_static == 'yes')

        include_args = ds['include']
        del ds['include']
        del ds['static']
        if is_static:
            ds['import_tasks'] = include_args
        else:
            ds['include_tasks'] = include_args

    if handler:
        ti = ansible.playbook.handler_task_include.HandlerTaskInclude.load(ds)
        validate_ansible_object(ti)
        return rep.Handler(
            name=ti.name,
            action=ti.action,
            args=ti.args,
            when=ti.when,
            loop=ti.loop,
            vars=extract_vars(ti.vars),
            register=ti.register,
            listen=ti.listen,
            raw=ds,
            # TODO!
            loop_control=None)
    else:
        ti = ansible.playbook.task_include.TaskInclude.load(ds)
        validate_ansible_object(ti)
        return rep.Task(
            name=ti.name,
            action=ti.action,
            args=ti.args,
            when=ti.when,
            loop=ti.loop,
            vars=extract_vars(ti.vars),
            register=ti.register,
            raw=ds,
            # TODO!
            loop_control=None)


def extract_task(ds: dict[str, AnsibleValue]) -> rep.Task:
    args_parser = ansible.parsing.mod_args.ModuleArgsParser(ds)
    (action, args, _) = args_parser.parse()
    if action in ansible.constants._ACTION_ALL_INCLUDE_IMPORT_TASKS or action in ansible.constants._ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES:
        return _extract_import_task(ds, action, args)

    raw_task = ansible.playbook.task.Task.load(ds)
    validate_ansible_object(raw_task)

    if raw_task.loop_control:
        raise FatalError('TODO: loop_control')

    return rep.Task(
        name=raw_task.name,
        action=raw_task.action,
        args=raw_task.args,
        when=raw_task.when,
        loop=raw_task.loop,
        vars=extract_vars(raw_task.vars),
        register=raw_task.register,
        raw=ds,
        # TODO!
        loop_control=None)


def extract_handler(ds: dict[str, AnsibleValue]) -> rep.Handler:
    args_parser = ansible.parsing.mod_args.ModuleArgsParser(ds)
    (action, args, _) = args_parser.parse()
    if action in ansible.constants._ACTION_ALL_INCLUDE_IMPORT_TASKS or action in ansible.constants._ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES:
        return _extract_import_task(ds, action, args, handler=True)

    raw_handler = ansible.playbook.handler.Handler.load(ds)
    validate_ansible_object(raw_handler)

    if raw_handler.loop_control:
        raise FatalError('TODO: loop_control')

    return rep.Handler(
        name=raw_handler.name,
        action=raw_handler.action,
        args=raw_handler.args,
        when=raw_handler.when,
        loop=raw_handler.loop,
        vars=extract_vars(raw_handler.vars),
        listen=raw_handler.listen,
        register=raw_handler.register,
        raw=ds,
        # TODO!
        loop_control=None)


class _PatchedPlay(ansible.playbook.play.Play):

    tasks: list[dict[str, AnsibleValue]]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # Similar to _PatchedBlock, remove loaders for tasks, handlers, and
        # roles because of Ansible's eager processing.
        self._load_tasks = None
        self._load_pre_tasks = None
        self._load_post_tasks = None
        self._load_handlers = None
        self._load_roles = None


# Workaround for error messages using the wrong class name.
_PatchedPlay.__name__ = 'Play'


def extract_play(ds: dict[str, AnsibleValue]) -> rep.Play:
    raw_play = _PatchedPlay()
    raw_play.load_data(ds)
    validate_ansible_object(raw_play)

    play = rep.Play(
        name=raw_play.name,
        hosts=raw_play.hosts,
        tasks=extract_list_of_tasks_or_blocks(raw_play.tasks, handlers=False),
        vars=extract_vars(raw_play.vars),
        raw=ds
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
        ds = parse_file(pb_path)
        assert isinstance(ds, list) and bool(ds), 'Malformed or empty playbook'

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
    except (ansible.errors.AnsibleError, AssertionError) as e:
        broken_files.append(rep.BrokenFile(path=file_path.relative, reason=str(e)))


def _safe_extract_all(extractor: Callable[[ProjectPath], ExtractedFileType], dir_path: ProjectPath, file_dict: dict[str, ExtractedFileType], broken_files: list[rep.BrokenFile]) -> None:
    for child_path in find_all_files(dir_path):
        _safe_extract(extractor, child_path, file_dict, broken_files)
