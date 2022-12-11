"""Extraction logic for structural model."""
from __future__ import annotations

from typing import Any, Callable, Literal, TypeVar, overload, TYPE_CHECKING

from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from itertools import chain
from pathlib import Path

from . import representation as rep, ansible_types as ans, loaders
from .helpers import ProjectPath, parse_file, validate_ansible_object, capture_output, find_all_files, find_file, FatalError, prevent_undesired_operations, convert_ansible_values


class ExtractionContext:
    """Context during extraction, to store broken files etc."""

    #: Whether extraction should be lenient. If true, the extractor will skip
    #: tasks or blocks that fail to extract, without skipping the entire file.
    #: If false, the entire file will be skipped instead.
    lenient: bool
    #: List of broken files which could not be parsed/extracted.
    broken_files: list[rep.BrokenFile]
    #: List of broken tasks or blocks that could not be parsed/extracted.
    broken_tasks: list[rep.BrokenTask]

    def __init__(self, lenient: bool) -> None:
        self.lenient = lenient
        self.broken_files = []
        self.broken_tasks = []


def _ansible_to_dict(obj: ans.FieldAttributeBase) -> dict[str, Any]:
    """Convert an Ansible object to a dictionary of its attributes.

    Used so that we can initialise the representation objects without having to
    manually specify each directive, while also being able to transform certain
    directive values.
    """

    attr_names = obj._attributes.keys()
    # For `include_role` actions, we can't use the field attributes since they
    # include action arguments, which we don't store specially. We'll instead
    # take them from its superclass.
    if isinstance(obj, ans.IncludeRole):
        attr_names = ans.TaskInclude._attributes.keys()

    return {attr_name: getattr(obj, attr_name) for attr_name in attr_names}


def extract_role_metadata_file(path: ProjectPath, ctx: ExtractionContext) -> rep.MetaFile:
    """Extract the structural representation of a metadata file."""

    ds, raw_ds = loaders.load_role_metadata(path)

    ds_platforms: list[dict[str, Any]] = ds['galaxy_info']['platforms']  # type: ignore
    ds_dependencies: list[str | dict[str, ans.AnsibleValue]] = ds['dependencies']  # type: ignore

    platforms = [rep.Platform(p['name'], v) for p in ds_platforms for v in p['versions']]
    dependencies = [dep for raw_dep in ds_dependencies if (dep := _extract_role_dependency(raw_dep, ctx, allow_new_style=True)) is not None]

    metablock = rep.MetaBlock(platforms=platforms, dependencies=dependencies, raw=raw_ds)
    metafile = rep.MetaFile(metablock=metablock, file_path=path.relative)
    metablock.parent = metafile
    return metafile


def _extract_role_dependency(ds: str | dict[str, ans.AnsibleValue], ctx: ExtractionContext, allow_new_style: bool = False) -> rep.RoleRequirement | None:
    try:
        ri, src_info, raw_ds = loaders.load_role_dependency(ds, allow_new_style=allow_new_style)
    except (ans.AnsibleError, loaders.LoadError) as e:
        if not ctx.lenient:
            raise
        ctx.broken_tasks.append(rep.BrokenTask(ds, str(e)))
        return None

    attrs = _ansible_to_dict(ri)

    return rep.RoleRequirement(
        **attrs,
        params=convert_ansible_values(ri._role_params),
        source_info=None if src_info is None else rep.RoleSourceInfo(**src_info),
        raw=raw_ds,
    )


def extract_variable_file(path: ProjectPath) -> rep.VariableFile:
    ds, raw_ds = loaders.load_variable_file(path)

    variables = extract_list_of_variables(ds)
    varfile = rep.VariableFile(file_path=path.relative, variables=variables, raw=raw_ds)
    return varfile


def extract_list_of_variables(ds: dict[str, ans.AnsibleValue]) -> dict[str, rep.AnyValue]:
    return {k: convert_ansible_values(v) for k, v in ds.items()}


def extract_tasks_file(path: ProjectPath, ctx: ExtractionContext, handlers: bool = False) -> rep.TaskFile:
    ds, raw_ds = loaders.load_tasks_file(path)

    content = extract_list_of_tasks_or_blocks(ds, ctx, handlers)  # type: ignore[call-overload]
    tf = rep.TaskFile(file_path=path.relative, tasks=content)
    for child in content:
        child.parent = tf
    return tf

@overload
def extract_list_of_tasks_or_blocks(ds: list[dict[str, ans.AnsibleValue]], ctx: ExtractionContext, handlers: Literal[True]) -> list[rep.Handler | rep.Block]: ...
@overload
def extract_list_of_tasks_or_blocks(ds: list[dict[str, ans.AnsibleValue]], ctx: ExtractionContext, handlers: Literal[False] = ...) -> list[rep.Task | rep.Block]: ...

def extract_list_of_tasks_or_blocks(ds: list[dict[str, ans.AnsibleValue]], ctx: ExtractionContext, handlers: Literal[True, False] = False) -> list[rep.Task | rep.Block] | list[rep.Handler | rep.Block]:
    content = []
    for inner_ds in ds:
        inner_result = extract_task_or_block(inner_ds, ctx, handlers)
        if inner_result is not None:
            content.append(inner_result)
    return content  # type: ignore[return-value]


@overload
def extract_task_or_block(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext, handlers: Literal[False]) -> rep.Task | rep.Block | None: ...
@overload
def extract_task_or_block(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext, handlers: Literal[True]) -> rep.Handler | rep.Block | None: ...

def extract_task_or_block(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext, handlers: Literal[True, False] = False) -> rep.Handler | rep.Task | rep.Block | None:
    if ans.Block.is_block(ds):
        return extract_block(ds, ctx, handlers)

    return extract_task(ds, ctx, handlers)


def extract_block(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext, handlers: Literal[True, False] = False) -> rep.Block | None:
    try:
        raw_block, raw_ds = loaders.load_block(ds)
    except (ans.AnsibleError, loaders.LoadError) as e:
        if not ctx.lenient:
            raise
        ctx.broken_tasks.append(rep.BrokenTask(ds, str(e)))
        return None

    attrs = _ansible_to_dict(raw_block)

    attrs['block'] = extract_list_of_tasks_or_blocks(raw_block.block, ctx, handlers=handlers)
    attrs['rescue'] = extract_list_of_tasks_or_blocks(raw_block.rescue, ctx, handlers=handlers)
    attrs['always'] = extract_list_of_tasks_or_blocks(raw_block.always, ctx, handlers=handlers)
    attrs['vars'] = extract_list_of_variables(raw_block.vars)

    block = rep.Block(**attrs, raw=raw_ds)

    for child in chain(block.block, block.rescue, block.always):
        child.parent = block

    return block


def _extract_loop_control(lc: ans.LoopControl | None) -> rep.LoopControl | None:
    if lc is None:
        return None

    validate_ansible_object(lc)
    return rep.LoopControl(**_ansible_to_dict(lc))


def extract_task(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext, as_handler: Literal[True, False]) -> rep.Task | rep.Handler | None:
    try:
        raw_task, raw_ds = loaders.load_task(ds, as_handler)
    except (ans.AnsibleError, loaders.LoadError) as e:
        if not ctx.lenient:
            raise
        ctx.broken_tasks.append(rep.BrokenTask(ds, str(e)))
        return None

    attrs = _ansible_to_dict(raw_task)
    attrs['args'] = convert_ansible_values(raw_task.args)
    attrs['loop_control'] = _extract_loop_control(raw_task.loop_control)
    attrs['vars'] = extract_list_of_variables(raw_task.vars)

    rep_cls = rep.Handler if as_handler else rep.Task

    return rep_cls(**attrs, raw=raw_ds, location=raw_ds.ansible_pos)  # type: ignore[no-any-return]


def extract_play(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext) -> rep.Play:
    raw_play, raw_ds = loaders.load_play(ds)

    attrs = _ansible_to_dict(raw_play)
    attrs['tasks'] = extract_list_of_tasks_or_blocks(raw_play.tasks or [], ctx, handlers=False)
    attrs['handlers'] = extract_list_of_tasks_or_blocks(raw_play.handlers or [], ctx, handlers=True)
    attrs['pre_tasks'] = extract_list_of_tasks_or_blocks(raw_play.pre_tasks or [], ctx, handlers=False)
    attrs['post_tasks'] = extract_list_of_tasks_or_blocks(raw_play.post_tasks or [], ctx, handlers=False)
    attrs['roles'] = [dep for raw_dep in (raw_play.roles or []) if (dep := _extract_role_dependency(raw_dep, ctx, allow_new_style=False)) is not None]
    attrs['vars'] = extract_list_of_variables(raw_play.vars)
    attrs['vars_prompt'] = [rep.VarsPrompt(**vp) for vp in raw_play.vars_prompt or []]  # type: ignore[arg-type, misc]

    play = rep.Play(**attrs, raw=raw_ds, location=raw_ds.ansible_pos)
    for child in chain(play.tasks, play.handlers, play.pre_tasks, play.post_tasks):
        child.parent = play
    return play


def extract_playbook_child(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext) -> rep.Play | None:
    if any(directive in ans.C._ACTION_IMPORT_PLAYBOOK for directive in ds):
        # Ignore import_playbook for now. The imported playbook can be checked as a separate entrypoint.
        return None
    else:
        return extract_play(ds, ctx)


def extract_playbook(path: Path, id: str, version: str, lenient: bool = True) -> rep.StructuralModel:
    """
    Extract a structural model from a playbook.

    :param      path:     The path to the playbook.
    :type       path:     Path
    :param      id:       The identifier for the playbook.
    :type       id:       str
    :param      version:  The version of the playbook.
    :type       version:  str
    :param      lenient:  Whether extraction should be lenient, i.e. ignoring
                          broken tasks/blocks.
    :type       lenient:  bool

    :returns:   Extracted structural model.
    :rtype:     StructuralModel
    """

    pb_path = ProjectPath.from_root(path)
    ctx = ExtractionContext(lenient)

    with capture_output() as output, prevent_undesired_operations():
        ds, raw_ds = loaders.load_playbook(pb_path)

        # Parse the plays in the playbook
        plays = []
        for play_ds in ds:
            try:
                play = extract_playbook_child(play_ds, ctx)
            except (ans.AnsibleError, loaders.LoadError) as e:
                if not ctx.lenient:
                    raise
                ctx.broken_tasks.append(rep.BrokenTask(play_ds, str(e)))
                continue

            if play is not None:
                plays.append(play)

    pb = rep.Playbook(plays=plays, raw=ds, broken_tasks=ctx.broken_tasks)
    for play in plays:
        play.parent = pb
    return rep.StructuralModel(root=pb, path=path, id=id, version=version, logs=output.getvalue())


def extract_role(path: Path, id: str, version: str, extract_all: bool = False, lenient: bool = True) -> rep.StructuralModel:
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
    :param      lenient:      Whether extracting should be lenient, i.e.
                              ignoring broken tasks/blocks.
    :type       lenient:      bool

    :returns:   Extracted structural model.
    :rtype:     StructuralModel
    """

    role_path = ProjectPath.from_root(path)
    ctx = ExtractionContext(lenient)

    # Extract all constituents
    task_files: dict[str, rep.TaskFile] = {}
    handler_files: dict[str, rep.TaskFile] = {}
    vars_files: dict[str, rep.VariableFile] = {}
    defaults_files: dict[str, rep.VariableFile] = {}
    meta_files: dict[str, rep.MetaFile] = {}

    with capture_output() as output, prevent_undesired_operations():
        meta_file_path = find_file(role_path, 'meta/main')
        _safe_extract(partial(extract_role_metadata_file, ctx=ctx), meta_file_path, meta_files, ctx)
        meta_file = next(iter(meta_files.values())) if meta_files else None

        if extract_all:
            get_dir = partial(ProjectPath, role_path.absolute)

            _safe_extract_all(partial(extract_tasks_file, ctx=ctx, handlers=False), get_dir('tasks'), task_files, ctx)
            _safe_extract_all(partial(extract_tasks_file, ctx=ctx, handlers=True), get_dir('handlers'), handler_files, ctx)
            _safe_extract_all(extract_variable_file, get_dir('vars'), vars_files, ctx)
            _safe_extract_all(extract_variable_file, get_dir('defaults'), defaults_files, ctx)
        else:
            def get_main_path(dirname: str) -> ProjectPath | None:
                return find_file(role_path.join(dirname), 'main')

            _safe_extract(partial(extract_tasks_file, ctx=ctx, handlers=False), get_main_path('tasks'), task_files, ctx)
            _safe_extract(partial(extract_tasks_file, ctx=ctx, handlers=True), get_main_path('handlers'), handler_files, ctx)
            _safe_extract(extract_variable_file, get_main_path('defaults'), defaults_files, ctx)
            _safe_extract(extract_variable_file, get_main_path('vars'), vars_files, ctx)

    role = rep.Role(
        task_files=task_files,
        handler_files=handler_files,
        role_var_files=vars_files,
        default_var_files=defaults_files,
        meta_file=meta_file,
        broken_files=ctx.broken_files,
        broken_tasks=ctx.broken_tasks,
    )

    return rep.StructuralModel(
        root=role,
        path=path,
        id=id,
        version=version,
        logs=output.getvalue()
    )


ExtractedFileType = TypeVar('ExtractedFileType')


def _safe_extract(extractor: Callable[[ProjectPath], ExtractedFileType], file_path: ProjectPath | None, file_dict: dict[str, ExtractedFileType], ctx: ExtractionContext) -> None:
    if file_path is None:
        return

    try:
        extracted_file = extractor(file_path)
        file_dict['/'.join(file_path.relative.parts[1:])] = extracted_file
    except (ans.AnsibleError, loaders.LoadError) as e:
        ctx.broken_files.append(rep.BrokenFile(path=file_path.relative, reason=str(e)))


def _safe_extract_all(extractor: Callable[[ProjectPath], ExtractedFileType], dir_path: ProjectPath, file_dict: dict[str, ExtractedFileType], ctx: ExtractionContext) -> None:
    if not dir_path.absolute.is_dir():
        return

    for child_path in find_all_files(dir_path):
        _safe_extract(extractor, child_path, file_dict, ctx)
