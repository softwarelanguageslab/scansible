"""Extraction logic for structural model."""

from __future__ import annotations

from typing import Callable, Literal, overload

from collections.abc import Iterable, Sequence
from functools import partial
from pathlib import Path

from ansible.parsing.yaml.objects import AnsibleBaseYAMLObject
from pydantic import ValidationError

from scansible.utils import actions

from . import ansible_types as ans
from . import ast, loaders
from .ast import ExtractionContext
from .helpers import (
    ProjectPath,
    capture_output,
    find_all_files,
    find_file,
    prevent_undesired_operations,
)


def _ansible_to_dict(obj: ans.FieldAttributeBase) -> dict[str, object]:
    """Convert an Ansible object to a dictionary of its attributes.

    Used so that we can initialise the representation objects without having to
    manually specify each directive, while also being able to transform certain
    directive values.
    """

    attrs = obj.fattributes
    # For `include_role` actions, we can't use the field attributes since they
    # include action arguments, which we don't store specially. We'll instead
    # take them from its superclass.
    if isinstance(obj, ans.IncludeRole):
        attrs = ans.TaskInclude.fattributes

    attr_names = {
        attr_name for attr_name, attr in attrs.items() if attr_name != attr.alias
    }

    return {attr_name: getattr(obj, attr_name) for attr_name in attr_names}


def _get_position(obj: object) -> ast.Position:
    if isinstance(obj, AnsibleBaseYAMLObject):
        file, line, column = obj.ansible_pos
        return ast.Position(file=Path(file), start_line=line, start_column=column)
    return ast.Position()


def extract_role_metadata_file(
    path: ProjectPath, ctx: ExtractionContext
) -> ast.MetaFile:
    """Extract the structural representation of a metadata file."""
    return ast.MetaFile.load(path, ctx)


def extract_variable_file(
    path: ProjectPath, ctx: ExtractionContext
) -> ast.VariableFile:
    return ast.VariableFile.load(path, ctx)


def extract_handler_file(path: ProjectPath, ctx: ExtractionContext) -> ast.HandlerFile:
    return ast.HandlerFile.load(path, ctx)


def extract_tasks_file(path: ProjectPath, ctx: ExtractionContext) -> ast.TaskFile:
    return ast.TaskFile.load(path, ctx)


@overload
def extract_list_of_tasks_or_blocks(
    ds: Sequence[dict[str, ans.AnsibleValue]],
    ctx: ExtractionContext,
    handlers: Literal[True],
) -> Sequence[ast.Handler]: ...


@overload
def extract_list_of_tasks_or_blocks(
    ds: Sequence[dict[str, ans.AnsibleValue]],
    ctx: ExtractionContext,
    handlers: Literal[False] = ...,
) -> Sequence[ast.Task | ast.Block]: ...


def extract_list_of_tasks_or_blocks(
    ds: Sequence[dict[str, ans.AnsibleValue]],
    ctx: ExtractionContext,
    handlers: Literal[True, False] = False,
) -> Sequence[ast.Task | ast.Block] | Sequence[ast.Handler]:
    if handlers:
        return list(_extract_handler_list(ds, ctx))
    else:
        return list(_extract_block_list(ds, ctx))


def _extract_handler_list(
    ds: Sequence[dict[str, ans.AnsibleValue]], ctx: ExtractionContext
) -> Iterable[ast.Handler]:
    for inner_ds in ds:
        inner_result = extract_handler(inner_ds, ctx)
        if inner_result is not None:
            yield inner_result


def _extract_block_list(
    ds: Sequence[dict[str, ans.AnsibleValue]], ctx: ExtractionContext
) -> Iterable[ast.Task | ast.Block]:
    for inner_ds in ds:
        inner_result = extract_task_or_block(inner_ds, ctx)
        if inner_result is not None:
            yield inner_result


def extract_task_or_block(
    ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext
) -> ast.Task | ast.Block | None:
    if ans.Block.is_block(ds):
        return extract_block(ds, ctx)

    return extract_task(ds, ctx)


def extract_block(
    ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext
) -> ast.Block | None:
    try:
        raw_block, raw_ds = loaders.load_block(ds)
    except (ans.AnsibleError, loaders.LoadError) as e:
        if not ctx.lenient:
            raise
        ctx.broken_tasks.append(ast.BrokenTask(raw=ds, reason=str(e)))
        return None

    attrs = _ansible_to_dict(raw_block)

    attrs["block"] = extract_list_of_tasks_or_blocks(raw_block.block, ctx)
    attrs["rescue"] = extract_list_of_tasks_or_blocks(raw_block.rescue, ctx)
    attrs["always"] = extract_list_of_tasks_or_blocks(raw_block.always, ctx)

    block = ast.Block(**attrs, position=_get_position(raw_ds))  # pyright: ignore[reportArgumentType]

    return block


def extract_task(
    ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext
) -> ast.Task | None:
    return _extract_task(ds, ctx, as_handler=False)


def extract_handler(
    ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext
) -> ast.Handler | None:
    return _extract_task(ds, ctx, as_handler=True)


@overload
def _extract_task(
    ds: dict[str, ans.AnsibleValue],
    ctx: ExtractionContext,
    as_handler: Literal[True],
) -> ast.Handler | None: ...
@overload
def _extract_task(
    ds: dict[str, ans.AnsibleValue],
    ctx: ExtractionContext,
    as_handler: Literal[False],
) -> ast.Task | None: ...
def _extract_task(
    ds: dict[str, ans.AnsibleValue],
    ctx: ExtractionContext,
    as_handler: Literal[True, False],
) -> ast.Task | ast.Handler | None:
    rep_cls = ast.Handler if as_handler else ast.Task
    return rep_cls.model_validate(ds, context=ctx)


def extract_play(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext) -> ast.Play:
    raw_play, raw_ds = loaders.load_play(ds)

    attrs = _ansible_to_dict(raw_play)
    attrs["tasks"] = extract_list_of_tasks_or_blocks(
        raw_play.tasks or [], ctx, handlers=False
    )
    attrs["handlers"] = extract_list_of_tasks_or_blocks(
        raw_play.handlers or [], ctx, handlers=True
    )
    attrs["pre_tasks"] = extract_list_of_tasks_or_blocks(
        raw_play.pre_tasks or [], ctx, handlers=False
    )
    attrs["post_tasks"] = extract_list_of_tasks_or_blocks(
        raw_play.post_tasks or [], ctx, handlers=False
    )
    attrs["vars"] = raw_play.vars
    attrs["vars_prompt"] = [
        ast.VarsPrompt(**vp, position=_get_position(vp))  # pyright: ignore[reportArgumentType]
        for vp in raw_play.vars_prompt or []
    ]

    play = ast.Play(**attrs, position=_get_position(raw_ds))  # pyright: ignore[reportArgumentType]
    return play


def extract_playbook_child(
    ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext
) -> ast.Play | None:
    if any(actions.is_import_playbook(directive) for directive in ds):
        # Ignore import_playbook for now. The imported playbook can be checked as a separate entrypoint.
        return None
    else:
        return extract_play(ds, ctx)


def extract_playbook_file(
    pb_path: ProjectPath, lenient: bool
) -> tuple[ast.Playbook, str]:
    ctx = ExtractionContext(lenient)

    with capture_output() as output, prevent_undesired_operations():
        ds, _ = loaders.load_playbook(pb_path)

        # Parse the plays in the playbook
        plays: list[ast.Play] = []
        for play_ds in ds:
            try:
                play = extract_playbook_child(play_ds, ctx)
            except (ans.AnsibleError, loaders.LoadError) as e:
                if not ctx.lenient:
                    raise
                ctx.broken_tasks.append(ast.BrokenTask(raw=play_ds, reason=str(e)))
                continue

            if play is not None:
                plays.append(play)

    pb = ast.Playbook(plays=plays, path=pb_path.relative, broken_tasks=ctx.broken_tasks)
    return pb, output.getvalue()


def extract_playbook(path: Path, lenient: bool = True) -> ast.AST:
    """
    Extract a structural model from a playbook.

    :param      path:     The path to the playbook.
    :type       path:     Path
    :param      lenient:  Whether extraction should be lenient, i.e. ignoring
                          broken tasks/blocks.
    :type       lenient:  bool

    :returns:   Extracted structural model.
    :rtype:     StructuralModel
    """

    pb_path = ProjectPath.from_root(path)
    pb, _ = extract_playbook_file(pb_path, lenient=lenient)

    return ast.AST(root=pb, path=path)


def extract_role(
    path: Path, extract_all: bool = False, lenient: bool = True
) -> ast.AST:
    """
    Extract a structural model from a role.

    :param      path:         The path to the role.
    :type       path:         Path
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
    task_files: dict[str, ast.TaskFile] = {}
    handler_files: dict[str, ast.HandlerFile] = {}
    vars_files: dict[str, ast.VariableFile] = {}
    defaults_files: dict[str, ast.VariableFile] = {}
    meta_files: dict[str, ast.MetaFile] = {}

    with capture_output(), prevent_undesired_operations():
        meta_file_path = find_file(role_path, "meta/main")
        _safe_extract(
            extract_role_metadata_file,
            meta_file_path,
            meta_files,
            ctx,
        )
        meta_file = next(iter(meta_files.values())) if meta_files else None

        if extract_all:
            get_dir = partial(ProjectPath, role_path.absolute)

            _safe_extract_all(
                extract_tasks_file,
                get_dir("tasks"),
                task_files,
                ctx,
            )
            _safe_extract_all(
                extract_handler_file,
                get_dir("handlers"),
                handler_files,
                ctx,
            )
            _safe_extract_all(
                extract_variable_file,
                get_dir("vars"),
                vars_files,
                ctx,
            )
            _safe_extract_all(
                extract_variable_file,
                get_dir("defaults"),
                defaults_files,
                ctx,
            )
        else:

            def get_main_path(dirname: str) -> ProjectPath | None:
                return find_file(role_path.join(dirname), "main")

            _safe_extract(
                extract_tasks_file,
                get_main_path("tasks"),
                task_files,
                ctx,
            )
            _safe_extract(
                extract_handler_file,
                get_main_path("handlers"),
                handler_files,
                ctx,
            )
            _safe_extract(
                extract_variable_file,
                get_main_path("defaults"),
                defaults_files,
                ctx,
            )
            _safe_extract(
                extract_variable_file,
                get_main_path("vars"),
                vars_files,
                ctx,
            )

    role = ast.Role(
        path=role_path.relative,
        task_files=ast.SourceFileMap(task_files.values(), prefix="tasks/"),
        handler_files=ast.SourceFileMap(handler_files.values(), prefix="handlers/"),
        role_var_files=ast.SourceFileMap(vars_files.values(), prefix="vars/"),
        default_var_files=ast.SourceFileMap(
            defaults_files.values(), prefix="defaults/"
        ),
        meta_file=meta_file,
        broken_files=ctx.broken_files,
        broken_tasks=ctx.broken_tasks,
    )

    return ast.AST(root=role, path=path)


type Extractor[T] = Callable[[ProjectPath, ExtractionContext], T]


def _safe_extract[T](
    extractor: Extractor[T],
    file_path: ProjectPath | None,
    file_dict: dict[str, T],
    ctx: ExtractionContext,
) -> None:
    if file_path is None:
        return

    try:
        extracted_file = extractor(file_path, ctx)
        file_dict["/".join(file_path.relative.parts[1:])] = extracted_file
    except (ans.AnsibleError, loaders.LoadError, ValidationError) as e:
        ctx.broken_files.append(ast.BrokenFile(path=file_path.relative, reason=str(e)))


def _safe_extract_all[T](
    extractor: Extractor[T],
    dir_path: ProjectPath,
    file_dict: dict[str, T],
    ctx: ExtractionContext,
) -> None:
    if not dir_path.absolute.is_dir():
        return

    for child_path in find_all_files(dir_path):
        _safe_extract(extractor, child_path, file_dict, ctx)
