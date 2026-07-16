"""Script to "stress-test" the AST by running the AST builder on real projects and logging errors."""
# DISCLAIMER: AI-generated

from __future__ import annotations

from typing import Callable, TextIO, cast

import csv
import re
import sys
import tarfile
import tempfile
from collections import Counter
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from itertools import groupby
from operator import itemgetter
from pathlib import Path

import click
import rich
import rich.console
import rich.progress
from ansible.errors import AnsibleParserError
from loguru import logger
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from scansible.representations import ast

#: Rules to ignore known-genuine validation errors, as (field-path regex,
#: error-detail regex) pairs. A ValidationError is only ignored if every one
#: of its sub-errors matches one of these rules. Extend this as new
#: known-genuine errors are identified during stress-test runs.
#:
#: Example: ignore a `loop` directive being given `None`:
#:     r"(^|\.)loop$", r"input=None"
IGNORED_ERRORS: Sequence[tuple[str, str]] = (
    # vars directive must be a dict.
    (r"\bvars$", r"input_type=AnsibleSequence"),
    # Many platforms are broken, fixing all outliers is useless.
    (r"^_RawPlatform\b", r""),
    # Specific extension to one project
    (r"\.task$", r"run_once_per vs fail"),
    (
        r"\.task$",
        r"Unsupported directives for \w+ tasks: (check_mode|delegate_to|notify|become)",
    ),
    (r"\.register\b", r"is a reserved keyword"),
    (r"\.register\b", r"not a valid expression"),  # means above check failed
    (r"MetaFile\.metablock$", r"input_type=NoneType"),
    (r"\.task$", r"dynamic vs include"),
    # Ignore for now but genuine error and known limitation, TODO
    (r"\.(gather_facts|no_log)\b", r"valid boolean"),
    (
        r"\.(gather_facts|no_log)\b",
        r"not a valid expression",
    ),  # means above check failed
)
RE_IGNORED_ERRORS = tuple(
    (re.compile(loc), re.compile(err)) for loc, err in IGNORED_ERRORS
)

#: Code locations with known faulty files that don't warrant a specific ignore reason.
IGNORED_LOCATIONS = {
    "EMCECS/ECS-CommunityEdition/ui/ansible/roles/CentOS_7_purge",
    "IBM/ansible-power-aix/playbooks/mksysb.yml",
    "IBM-Security/isam-ansible-roles/base/install_fixpacks",
    "IBM/community-automation/ansible/roles/aws_cli_install",
}

#: Label used to count ignores of AnsibleParserError, which isn't governed by
#: an IGNORED_ERRORS rule (it's always ignored).
PARSING_ERROR_LABEL = "<parsing error>"


def _loc_str(exc: ValidationError, loc: tuple[int | str, ...]) -> str:
    """Render a pydantic error's `loc` tuple as a dotted field path."""
    return ".".join([exc.title, *map(str, loc)])


def _err_str(err: ErrorDetails, short: bool = False) -> str:
    """Render a pydantic error's type/message/input as a single matchable string."""
    msg = f"{err['type']}: {err['msg']}; input_type={type(err['input']).__name__}"  # pyright: ignore[reportAny]
    if not short:
        msg += "; input={err['input']!r})"
    return msg


def _rule_label(field_pat: re.Pattern[str], msg_pat: re.Pattern[str]) -> str:
    """Human-readable label for an IGNORED_ERRORS rule, used as its counter key."""
    return f"{field_pat.pattern!r} / {msg_pat.pattern!r}"


def _is_ignored(location: str, exc: Exception, ignore_counts: Counter[str]) -> bool:
    """Whether an exception raised/recorded during extraction should be ignored.

    Parsing errors are always genuine dataset issues, not AST bugs, and are
    always ignored. A ValidationError is ignored only if every one of its
    sub-errors matches an entry in `IGNORED_ERRORS`. Each matching rule's
    trigger count is tallied in `ignore_counts`, so rules that fire too often
    (a sign of an overly broad ignore) can be spotted in the final report.
    """
    if location in IGNORED_LOCATIONS:
        return True
    if isinstance(exc, AnsibleParserError):
        ignore_counts[PARSING_ERROR_LABEL] += 1
        return True
    if not isinstance(exc, ValidationError):
        return False

    errors = exc.errors()
    if not errors:
        return False

    matched_labels: list[str] = []
    for err in errors:
        label = next(
            (
                _rule_label(field_pat, msg_pat)
                for field_pat, msg_pat in RE_IGNORED_ERRORS
                if field_pat.search(_loc_str(exc, err["loc"]))
                and msg_pat.search(_err_str(err))
            ),
            None,
        )
        if label is None:
            return False
        matched_labels.append(label)

    ignore_counts.update(matched_labels)
    return True


@contextmanager
def _resolve_repo(data_dir: Path, repo: str) -> Generator[Path]:
    """Resolve `repo` (an "owner/repo"-style path) to an on-disk directory.

    If `data_dir/repo` is a plain directory, it's used directly. Otherwise,
    `data_dir/repo.tar.gz` is extracted into a temporary directory (cleaned up
    on context exit) and the extracted `repo`-named directory within it is used.
    """
    repo_dir = data_dir / repo
    if repo_dir.is_dir():
        yield repo_dir
        return

    archive = data_dir / f"{repo}.tar.gz"
    if not archive.is_file():
        raise FileNotFoundError(f"Neither {repo_dir} nor {archive} exist")

    with tempfile.TemporaryDirectory(prefix="stress-test-ast-") as tmp:
        with tarfile.open(archive) as tf:
            tf.extractall(tmp, filter="data")
        yield Path(tmp) / repo_dir.name


def _extract(path: Path, entrypoint_type: str) -> ast.AST:
    """Run the given entrypoint through the AST builder, in lenient mode."""
    if entrypoint_type == "playbook":
        return ast.extract_playbook(path, lenient=True)
    return ast.extract_role(path, lenient=True, extract_all=True)


@click.command()
@click.argument("entrypoints_csv", type=click.File())
@click.argument(
    "data_dir",
    type=click.Path(file_okay=False, exists=True, resolve_path=True, path_type=Path),
)
@click.option(
    "--fail-after",
    type=int,
    default=10,
    show_default=True,
    help="Stop after this many un-ignored errors and exit non-zero.",
)
def main(entrypoints_csv: TextIO, data_dir: Path, fail_after: int) -> None:
    """Stress-test the AST builder against a real dataset of playbooks/roles.

    ENTRYPOINTS_CSV: CSV with fields `repo`, `relative_path`, `type`.

    DATA_DIR: Directory containing the dataset, laid out as DATA_DIR/owner/repo
    (a directory) or DATA_DIR/owner/repo.tar.gz (an archive extracting to a
    single top-level `repo` directory).
    """
    logger.remove()
    _ = logger.add(sys.stderr, level="INFO")

    entrypoints: list[dict[str, str]] = sorted(
        csv.DictReader(entrypoints_csv), key=itemgetter("repo")
    )
    error_console = rich.console.Console(stderr=True)

    error_count = 0
    ignored_count = 0
    ignore_counts: Counter[str] = Counter()

    with rich.progress.Progress(
        rich.progress.TextColumn("[progress.description]{task.description}"),
        rich.progress.BarColumn(),
        rich.progress.MofNCompleteColumn(),
        rich.progress.TimeRemainingColumn(),
        rich.progress.TimeElapsedColumn(),
        console=error_console,
    ) as progress:
        task_id = progress.add_task("Stress-testing AST", total=len(entrypoints))

        for repo, repo_entrypoints_iter in groupby(
            entrypoints, key=cast(Callable[[object], str], itemgetter("repo"))
        ):
            repo_entrypoints = list(repo_entrypoints_iter)

            try:
                with _resolve_repo(data_dir, repo) as repo_dir:
                    for entrypoint in repo_entrypoints:
                        progress.advance(task_id)
                        entrypoint_path = repo_dir / entrypoint["relative_path"]
                        location = f"{repo}/{entrypoint['relative_path']}"
                        progress.update(task_id, description=location)

                        try:
                            result = _extract(entrypoint_path, entrypoint["type"])
                        except Exception as exc:
                            if _is_ignored(location, exc, ignore_counts):
                                ignored_count += 1
                                continue
                            error_console.print(f"[bold red]{location}[/bold red]")
                            error_console.print_exception(max_frames=1)
                            error_count += 1
                            if error_count >= fail_after:
                                break
                            continue

                        broken = [*result.broken_files, *result.broken_tasks]
                        entry_had_error = False
                        for b in broken:
                            if _is_ignored(location, b.reason, ignore_counts):
                                ignored_count += 1
                                continue

                            if isinstance(b.reason, ValidationError):
                                error_console.print(
                                    f"[bold red]{location}[/bold red]: Validation error"
                                )
                                for err in b.reason.errors():
                                    error_console.print(
                                        " " * 2, _loc_str(b.reason, err["loc"])
                                    )
                                    error_console.print(
                                        " " * 4, _err_str(err, short=True)
                                    )
                            else:
                                error_console.print(
                                    f"[bold red]{location}[/bold red]: {b.reason}"
                                )
                            entry_had_error = True

                        if entry_had_error:
                            error_count += 1
                            if error_count >= fail_after:
                                break
            except FileNotFoundError as exc:
                error_console.print(f"[bold red]{repo}: {exc}[/bold red]")
                error_count += 1
                progress.advance(task_id, len(repo_entrypoints))

            if error_count >= fail_after:
                error_console.print(
                    f"[bold red]Stopping: reached {fail_after} errors[/bold red]"
                )
                break

    rich.print(
        f"Processed {len(entrypoints)} entrypoints: {error_count} errors, {ignored_count} ignored."
    )
    if ignore_counts:
        rich.print("Ignores triggered (a high count may indicate a bad ignore rule):")
        for label, count in ignore_counts.most_common():
            rich.print(f"  {count:>6}  {label}")
    sys.exit(1 if error_count else 0)


if __name__ == "__main__":
    main()
