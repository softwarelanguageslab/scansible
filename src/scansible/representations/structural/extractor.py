"""Extraction logic for structural model."""
from __future__ import annotations

from typing import Callable, Literal, TypeVar, overload

from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from pathlib import Path

import ansible
import ansible.playbook
import ansible.playbook.task
import ansible.playbook.block
import ansible.playbook.handler
import ansible.playbook.play
import ansible.parsing.dataloader
import ansible.parsing.mod_args

from . import representation as rep


# Patch the ModuleArgsParser so that it doesn't verify whether the action exist.
# Otherwise it'll complain on non-builtin actions
old_mod_args_parse = ansible.parsing.mod_args.ModuleArgsParser.parse
ansible.parsing.mod_args.ModuleArgsParser.parse = lambda self, skip_action_validation=False: old_mod_args_parse(self, skip_action_validation=True)  # type: ignore[assignment]


class FatalError(Exception):
    """Fatal error to stop all extraction."""
    pass


class ProjectPath:
    root: Path
    relative: Path

    def __init__(self, root_path: Path, file_path: Path | str) -> None:
        assert root_path.is_absolute()
        self.root = root_path

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if file_path.is_absolute():
            self.relative = file_path.relative_to(root_path)
        else:
            self.relative = file_path

    @classmethod
    def from_root(cls, root_path: Path) -> ProjectPath:
        return cls(root_path, '.')

    def join(self, other: Path | str | ProjectPath) -> ProjectPath:
        if isinstance(other, ProjectPath):
            assert other.root == self.root, 'Project paths with different roots'
            other = other.relative
        elif isinstance(other, str):
            other = Path(other)

        return ProjectPath(self.root, other)


    @property
    def absolute(self) -> Path:
        return (self.root / self.relative).resolve()


def _parse_file(path: ProjectPath) -> object:
    """Parse a YAML file using Ansible's parser."""
    loader = ansible.parsing.dataloader.DataLoader()
    return loader.load_from_file(str(path.absolute))


def _validate_ansible_object(obj: ansible.playbook.base.FieldAttributeBase) -> None:
    """Validate and mutate the given Ansible object."""

    # We have to reimplement Ansible's logic because it eagerly templates certain
    # expressions. We don't want that.
    for (name, attribute) in obj._valid_attrs.items():
        value = getattr(obj, name)
        if value is None:
            continue
        if attribute.isa == 'class':
            assert isinstance(value, ansible.playbook.base.FieldAttributeBase)
            _validate_ansible_object(value)
            continue

        # templar argument is only used when attribute.isa is a class, which we
        # handle specially above.
        validated_value = obj.get_validated_value(name, attribute, value, None)
        setattr(obj, name, validated_value)


def extract_role_metadata_file(path: ProjectPath) -> rep.MetaFile:
    """Extract the structural representation of a metadata file."""

    ds = _parse_file(path)
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


def _extract_meta_platforms(meta: dict[str, object]) -> list[rep.Platform]:
    galaxy_info = meta.get('galaxy_info', {})
    assert isinstance(galaxy_info, dict), f'galaxy_info expected to be a dictionary, got {galaxy_info!r}'
    raw_platforms = galaxy_info.get('platforms', [])
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


def _extract_meta_dependencies(meta: dict[str, object]) -> list[rep.Dependency]:
    deps = meta.get('dependencies', [])
    if deps:
        raise FatalError(f'TODO: Dependencies: {deps}')

    return []


def extract_variable_file(path: ProjectPath) -> rep.VariableFile:
    ds = _parse_file(path)
    assert isinstance(ds, dict), 'Expected variable file to contain a dictionary'

    variables = extract_vars(ds)
    varfile = rep.VariableFile(file_path=path.relative, variables=variables)
    for v in variables:
        v.parent = varfile
    return varfile


def extract_vars(ds: dict[str, rep.AnyValue]) -> list[rep.Variable]:
    return [rep.Variable(name=k, value=v) for k, v in ds.items()]


def extract_tasks_file(path: ProjectPath, handlers: bool = False) -> rep.TaskFile:
    ds = _parse_file(path)
    assert isinstance(ds, list), 'Expected task file to be a list'

    content = extract_list_of_tasks_or_blocks(ds, handlers)  # type: ignore[call-overload]
    tf = rep.TaskFile(file_path=path.relative, tasks=content)
    for child in content:
        child.parent = tf
    return tf

@overload
def extract_list_of_tasks_or_blocks(ds: list[dict[str, rep.AnyValue]], handlers: Literal[False]) -> list[rep.Task | rep.Block]: ...
@overload
def extract_list_of_tasks_or_blocks(ds: list[dict[str, rep.AnyValue]], handlers: Literal[True]) -> list[rep.Handler]: ...

def extract_list_of_tasks_or_blocks(ds: list[dict[str, rep.AnyValue]], handlers: bool = False) -> list[rep.Task | rep.Block] | list[rep.Handler]:
    content = []
    for inner_ds in ds:
        assert isinstance(inner_ds, dict) and all(isinstance(k, str) for k in inner_ds), 'Task list content must be a list of dictionaries'
        content.append(extract_task_or_block(inner_ds, handlers))  # type: ignore[call-overload]
    return content


@overload
def extract_task_or_block(ds: dict[str, rep.AnyValue], handlers: Literal[False]) -> rep.Task | rep.Block: ...
@overload
def extract_task_or_block(ds: dict[str, rep.AnyValue], handlers: Literal[True]) -> rep.Handler: ...

def extract_task_or_block(ds: dict[str, rep.AnyValue], handlers: bool = False) -> rep.Handler | rep.Task | rep.Block:
    if ansible.playbook.block.Block.is_block(ds):
        if handlers:
            raise FatalError('Found a block in what is supposed to be a handler, TODO?')
        return extract_block(ds)

    return extract_handler(ds) if handlers else extract_task(ds)


class _PatchedBlock(ansible.playbook.block.Block):

    block: list[dict[str, rep.AnyValue]]  # type: ignore[assignment]
    rescue: list[dict[str, rep.AnyValue]]  # type: ignore[assignment]
    always: list[dict[str, rep.AnyValue]]  # type: ignore[assignment]

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


def extract_block(ds: dict[str, rep.AnyValue]) -> rep.Block:
    raw_block = _PatchedBlock(ds)
    raw_block.load_data(ds)
    _validate_ansible_object(raw_block)

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


def extract_task(ds: dict[str, rep.AnyValue]) -> rep.Task:
    raw_task = ansible.playbook.task.Task.load(ds)
    _validate_ansible_object(raw_task)

    if raw_task.loop_control:
        raise FatalError('TODO: loop_control')

    return rep.Task(
        name=raw_task.name,
        action=raw_task.action,
        args=raw_task.args,
        when=raw_task.when,
        loop=raw_task.loop,
        vars=extract_vars(raw_task.vars),
        raw=ds,
        # TODO!
        loop_control=None)


def extract_handler(ds: dict[str, rep.AnyValue]) -> rep.Handler:
    raw_handler = ansible.playbook.handler.Handler.load(ds)
    _validate_ansible_object(raw_handler)

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
        raw=ds,
        # TODO!
        loop_control=None)


def find_file(dir_path: ProjectPath, file_name: str) -> ProjectPath | None:
    loader = ansible.parsing.dataloader.DataLoader()
    # DataLoader.find_vars_files is misnamed.
    found_paths = loader.find_vars_files(str(dir_path.absolute), file_name, allow_dir=False)
    assert len(found_paths) <= 1, f'Found multiple files for {file_name} in {dir_path.relative}'

    if not found_paths:
        return None

    found_path = found_paths[0]
    return dir_path.join(found_path.decode('utf-8'))


def find_all_files(dir_path: ProjectPath) -> list[ProjectPath]:
    results = []
    for child in dir_path.absolute.iterdir():
        child_path = dir_path.join(child)
        if child.is_file() and child.suffix in ansible.constants.YAML_FILENAME_EXTENSIONS:
            results.append(child_path)
        elif child.is_dir():
            results.extend(find_all_files(child_path))

    return results


ExtractedFileType = TypeVar('ExtractedFileType')


def safe_extract(extractor: Callable[[ProjectPath], ExtractedFileType], file_path: ProjectPath | None, file_dict: dict[str, ExtractedFileType], broken_files: list[rep.BrokenFile]) -> None:
    if file_path is None:
        return

    try:
        extracted_file = extractor(file_path)
        file_dict['/'.join(file_path.relative.parts[1:])] = extracted_file
    except (ansible.errors.AnsibleError, AssertionError) as e:
        broken_files.append(rep.BrokenFile(path=file_path.relative, reason=str(e)))


def safe_extract_all(extractor: Callable[[ProjectPath], ExtractedFileType], dir_path: ProjectPath, file_dict: dict[str, ExtractedFileType], broken_files: list[rep.BrokenFile]) -> None:
    for child_path in find_all_files(dir_path):
        safe_extract(extractor, child_path, file_dict, broken_files)


class _LogCapture:
    def __init__(self) -> None:
        self.logs: list[str] = []

    def write(self, buf: str) -> int:
        self.logs.append(buf)
        return len(buf)

    def flush(self) -> None:
        pass


class _PatchedPlay(ansible.playbook.play.Play):

    tasks: list[dict[str, rep.AnyValue]]

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


def extract_play(ds: dict[str, rep.AnyValue]) -> rep.Play:
    raw_play = _PatchedPlay()
    raw_play.load_data(ds)
    _validate_ansible_object(raw_play)

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

    log_capture = _LogCapture()
    with redirect_stdout(log_capture), redirect_stderr(log_capture):  # type: ignore[type-var]
        ds = _parse_file(pb_path)
        assert isinstance(ds, list) and bool(ds), 'Malformed or empty playbook'

        # Parse the plays in the playbook
        plays = [extract_play(play_ds) for play_ds in ds]

    pb = rep.Playbook(plays=plays, logs=log_capture.logs, raw=ds)
    for play in plays:
        play.parent = pb
    return rep.StructuralModel(root=pb, path=path, id=id, version=version)


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

    log_capture = _LogCapture()
    with redirect_stdout(log_capture), redirect_stderr(log_capture):  # type: ignore[type-var]
        meta_file_path = find_file(role_path, 'meta/main')
        safe_extract(extract_role_metadata_file, meta_file_path, meta_files, broken_files)
        meta_file = next(iter(meta_files.values())) if meta_files else None

        if extract_all:
            get_dir = partial(ProjectPath, role_path.absolute)

            safe_extract_all(partial(extract_tasks_file, handlers=False), get_dir('tasks'), task_files, broken_files)
            safe_extract_all(partial(extract_tasks_file, handlers=True), get_dir('handlers'), handler_files, broken_files)
            safe_extract_all(extract_variable_file, get_dir('vars'), vars_files, broken_files)
            safe_extract_all(extract_variable_file, get_dir('defaults'), defaults_files, broken_files)
        else:
            def get_main_path(dirname: str) -> ProjectPath | None:
                return find_file(role_path, 'meta/main')

            safe_extract(partial(extract_tasks_file, handlers=False), get_main_path('tasks'), task_files, broken_files)
            safe_extract(partial(extract_tasks_file, handlers=True), get_main_path('handlers'), handler_files, broken_files)
            safe_extract(extract_variable_file, get_main_path('defaults'), defaults_files, broken_files)
            safe_extract(extract_variable_file, get_main_path('vars'), vars_files, broken_files)

    role = rep.Role(
        task_files=task_files,
        handler_files=handler_files,
        role_var_files=vars_files,
        default_var_files=defaults_files,
        meta_file=meta_file,
        broken_files=broken_files,
        logs=log_capture.logs,
    )

    return rep.StructuralModel(
        root=role,
        path=path,
        id=id,
        version=version,
    )

