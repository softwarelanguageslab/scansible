from __future__ import annotations

from typing import Iterable, Iterator, cast

import json
import shutil
import sys
import tempfile
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

from git import Repo
from loguru import logger

from .extractor.main import extract_structural_graph
from .io import graphml, graphviz, neo4j
from .io.structural_models import parse_role

SuccessResult = tuple[str, str, str, str, str, str, str]
FailResult = tuple[str, Exception]


def extract_one(
    args: tuple[str, str, Path], log_reset: bool = True
) -> SuccessResult | FailResult:
    log_stream = StringIO()
    if log_reset:
        logger.remove()
        logger.add(log_stream, level="DEBUG")
    role_id, role_version, role_path = args
    try:
        ctx = extract_structural_graph(role_path, role_id, role_version)
        neo4j_str = neo4j.dump_graph(ctx.graph)
        graphml_str = graphml.dump_graph(ctx.graph)
        dot_str = graphviz.dump_graph(ctx.graph)
        error_str = "\n".join(ctx.graph.errors)
        visibility_dump = ctx.visibility_information.dump()
        log_stream.seek(0)
        log_str = log_stream.read()
        return (
            role_id,
            neo4j_str,
            graphml_str,
            dot_str,
            visibility_dump,
            error_str,
            log_str,
        )
    except Exception as e:
        # print(f'{role_id}: {type(e).__name__}: {e}')
        logger.error(f"{type(e).__name__}: {e}")
        logger.exception(e)
        return role_id, e
    finally:
        if log_reset:
            logger.remove()


@contextmanager
def tmp_copy_repo(input_path: Path) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmpd:
        shutil.copytree(
            input_path,
            tmpd,
            dirs_exist_ok=True,
            symlinks=True,
            ignore_dangling_symlinks=True,
        )
        yield Path(tmpd)


CommitInfo = tuple[
    str, str, list[str]
]  # SHA1, message, parents. Rest of the info should be in the dataset already


def iter_commits_and_checkout(repo_path: Path) -> Iterable[CommitInfo]:
    repo = Repo(repo_path)
    assert not repo.head.is_detached, "Bad repo: Detached head"
    try:
        repo.commit("HEAD")
    except Exception as e:
        if "Ref 'HEAD' did not resolve to an object" in str(e):
            # Empty repository
            return
        raise

    queue = [repo.commit("HEAD")]
    seen_shas: set[str] = set()
    head_sha = queue[0].hexsha

    # repo.git.reset('--hard HEAD')

    for commit in queue:
        repo.git.checkout(commit, "--force")

        sha = commit.hexsha if commit.hexsha != head_sha else "HEAD"
        parent_shas = [p.hexsha for p in commit.parents]
        info = (sha, str(commit.message), parent_shas)

        queue.extend(
            parent for parent in commit.parents if parent.hexsha not in seen_shas
        )
        seen_shas.update(parent_shas)
        yield info


def write_result_file(base_path: Path, sha: str, contents: str, extension: str) -> Path:
    out_path = base_path.joinpath(*sha[:3]) / (sha + extension)
    out_path.parent.mkdir(exist_ok=True, parents=True)
    out_path.write_text(contents)
    return out_path


def extract_full_repo(
    args: tuple[str, Path, Path]
) -> tuple[str, list[str], list[str], list[CommitInfo]]:
    try:
        return _extract_full_repo(args)
    except BaseException as e:
        print(f"{args[0]}: {e}")
        return args[0], [], [str(e)], []


def _extract_full_repo(
    args: tuple[str, Path, Path]
) -> tuple[str, list[str], list[str], list[CommitInfo]]:
    role_id, role_path, output_path = args

    tmp_repo = Repo(role_path)
    assert not tmp_repo.head.is_detached, "Bad repo: Detached head"

    if (output_path / "status" / (role_id + ".json")).is_file():
        return load_from_previous_run(role_id, output_path)

    outs = {
        subdir: (output_path / subdir / role_id)
        for subdir in ("graphml", "errors", "aux")
    }
    for out_dir in outs.values():
        if out_dir.is_dir():
            shutil.rmtree(out_dir)
        out_dir.mkdir(exist_ok=True, parents=True)

    with tmp_copy_repo(role_path) as repo_path:
        commit_infos: list[CommitInfo] = []
        exceptions: list[str] = []
        success_paths: list[str] = []
        for commit_info in iter_commits_and_checkout(repo_path):
            sha = commit_info[0]
            commit_infos.append(commit_info)
            result = extract_one((role_id, sha, repo_path))
            if len(result) == 2:
                _, exc = cast(FailResult, result)
                write_result_file(outs["errors"], sha, str(exc), ".txt")
                exceptions.append(str(exc))
                continue

            _, neo4j_str, graphml_str, dot_str, vis_str, error_str, log_str = cast(
                SuccessResult, result
            )
            # write_result_file(outs['neo4j'], sha, neo4j_str, '.txt')
            graphml_path = write_result_file(outs["graphml"], sha, graphml_str, ".xml")
            # write_result_file(outs['dot'], sha, dot_str, '.dot')
            # write_result_file(outs['logs'], sha, log_str, '.txt')
            write_result_file(outs["errors"], sha, error_str, ".txt")
            write_result_file(outs["aux"], sha, vis_str, ".vis.json")
            success_paths.append(str(graphml_path))

    assert len(exceptions) + len(success_paths) == len(
        commit_infos
    ), "Missing commits?!"

    # Marks as successful
    (output_path / "status" / (role_id + ".json")).write_text(json.dumps(commit_infos))
    return (role_id, success_paths, exceptions, commit_infos)


def load_from_previous_run(
    role_id: str, output_path: Path
) -> tuple[str, list[str], list[str], list[CommitInfo]]:
    commit_infos = json.loads(
        (output_path / "status" / (role_id + ".json")).read_text()
    )
    all_graph_xmls = [
        f for f in (output_path / "graphml" / role_id).glob("**/*.xml") if f.is_file()
    ]
    all_graph_shas = {f.stem for f in all_graph_xmls}
    assert len(all_graph_shas) == len(all_graph_xmls)
    all_errors = [
        f for f in (output_path / "errors" / role_id).glob("**/*.txt") if f.is_file()
    ]
    all_error_shas = {f.stem for f in all_errors}
    fatal_error_shas = all_error_shas - all_graph_shas
    if not len(fatal_error_shas | all_graph_shas) == len(commit_infos):
        print(
            f"Missing commits?! {len(fatal_error_shas | all_graph_shas)} vs {len(commit_infos)}"
        )

    errors = [
        load_error(role_id, output_path, error_sha) for error_sha in fatal_error_shas
    ]
    return role_id, [str(f) for f in all_graph_xmls], errors, commit_infos


def load_error(role_id: str, output_path: Path, error_sha: str) -> str:
    error_path = (output_path / "errors" / role_id).joinpath(*error_sha[:3]) / (
        error_sha + ".txt"
    )
    return error_path.read_text()
