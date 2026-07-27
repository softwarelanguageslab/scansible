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
from loguru import logger
from pydantic import ValidationError
from pydantic_core import ErrorDetails
from rich.panel import Panel
from rich.syntax import Syntax
from ruamel.yaml import YAMLError

from scansible.representations import ast
from scansible.utils import Positioned

#: Rules to ignore known-genuine validation errors, as (field-path regex,
#: error-detail regex) pairs. A ValidationError is only ignored if every one
#: of its sub-errors is part of a group that matches one of these rules (see
#: `_group_errors`): sub-errors are first grouped by offending value, since a
#: field typed as a plain `Union` produces one sub-error per variant tried
#: (all for the same value). A rule matches a group if its field-path regex
#: matches any member's loc and its message regex matches any member's
#: message — so a single rule, targeting just one variant's message, is
#: enough to silence a whole multi-variant group. Extend this as new
#: known-genuine errors are identified during stress-test runs.
#:
#: Example: ignore a `loop` directive being given `None`:
#:     r"(^|\.)loop$", r"input=None"
IGNORED_ERRORS: Sequence[tuple[str, str]] = (
    # vars directive must be a dict.
    (r"\bvars$", r"input_type=YamlSeq"),
    # Many platforms are broken, fixing all outliers is useless.
    (r"^_RawPlatform\b", r""),
    (r"MetaFile\.metablock$", r"galaxy_info.+input_type=(YamlNone|NoneType)"),
    # Specific extension to one project
    (r"\.task$", r"run_once_per vs fail"),
    (
        r"\.task$",
        r"Unsupported directives for \w+ tasks: (check_mode|delegate_to|notify|become|remote_user|changed_when)",
    ),
    (r"\.register\b", r"is a reserved keyword"),
    (r"\.register\b", r"valid identifier"),
    (r"MetaFile\.metablock$", r"input_type=(YamlNone|NoneType)"),
    (r"\.task$", r"dynamic vs include"),
    (r"\.task$", r"import_tasks with static: no"),
    (r"(when|until)\b", "Conditions must not contain any Jinja2 brace syntax"),
    (r"(when|until)\b", "Template Syntax Error:"),
    (r"VariableFile.variables$", r"input_type=YamlSeq"),
    (r"task\.environment", r"Jinja2 delimiters.+input_type=YamlStr"),
)
RE_IGNORED_ERRORS = tuple(
    (re.compile(loc), re.compile(err)) for loc, err in IGNORED_ERRORS
)

#: Code locations with known faulty files that don't warrant a specific ignore reason.
IGNORED_LOCATIONS = {
    "EMCECS/ECS-CommunityEdition/ui/ansible/roles/CentOS_7_purge",
    "EMCECS/ECS-CommunityEdition/ui/ansible/roles/common_sync_caches_by_copy",
    "IBM/ansible-power-aix/playbooks/mksysb.yml",
    "IBM-Security/isam-ansible-roles/base/install_fixpacks",
    "IBM-Security/isam-ansible-roles/search_mapping_rule",
    "IBM/community-automation/ansible/roles/aws_cli_install",
    "RedHatGov/redhatgov.workshops/jboss-aws-setup/roles/rhel-common",
    "AAROC/DevOps/Ansible/roles/worker-node",
    "ansible/ansible-lint/examples/playbooks/conflicting_action.yml",
    "ansible/ansible-examples/language_features/selective_file_sources.yml",
    "ansible/ansible-lint/examples/playbooks/example.yml",  # None task, technically valid but ignored edge case
    "ansible/ansible-lint/examples/playbooks/jinja2-when-failure.yml",
    "ansible/ansible-lint/examples/playbooks/jinja2-when-success.yml",
    "ansible/ansible-lint/examples/playbooks/syntax-error.yml",
    "apache/fluo-muchos/ansible/roles/common",
    "bennojoy/ntp/.",
    "devopsschool-training-notes/Ansible-astrazeneca-June-2020/Kannan/Day-3/AVLEp3/var2.yaml",
    "devopsschool-training-notes/Ansible-astrazeneca-June-2020/Lakshminarayanan/Day3/AVLEp3/var2.yaml",
    "devopsschool-training-notes/Ansible-astrazeneca-June-2020/Madhu/rolesprj/day4assign",
    "rhevm-qe-automation/ovirt-ansible/roles/ovirt-engine-db-dump",
    "redhat-gpte-devopsautomation/FTL/devel/run-locally.yml",
    "pulibrary/princeton_ansible/playbooks/nginxplus_production_rebuild.yml",
    "project-sunbird/sunbird-data-pipeline/ansible/yarn_stop.yml",
}

#: Label used to count ignores of YAMLError, which isn't governed by
#: an IGNORED_ERRORS rule (it's always ignored).
PARSING_ERROR_LABEL = "<parsing error>"


def _loc_str(exc: ValidationError, loc: tuple[int | str, ...]) -> str:
    """Render a pydantic error's `loc` tuple as a dotted field path."""
    return ".".join([exc.title, *map(str, loc)])


def _err_str(err: ErrorDetails) -> str:
    """Render a pydantic error's type/message/input as a single matchable string, for ignore-rule matching."""
    return (
        f"{err['type']}: {err['msg']}; "
        f"input_type={type(err['input']).__name__}; input={err['input']!r}"  # pyright: ignore[reportAny]
    )


def _group_key(err: ErrorDetails) -> object:
    """Key identifying the value a sub-error is about.

    A field typed as a plain (non-discriminated) `Union` produces one
    sub-error per variant pydantic tried, all for the same offending value.
    Prefer the value's source position (hashable, value-comparable) over
    `id()`, which would risk conflating two unrelated fields that happen to
    both fail on a shared singleton (e.g. `None`).
    """
    value = err["input"]  # pyright: ignore[reportAny]
    if isinstance(value, Positioned) and not value.__position__.is_synthetic:
        return value.__position__
    return id(value)


def _group_errors(errors: Sequence[ErrorDetails]) -> list[list[ErrorDetails]]:
    """Group a ValidationError's sub-errors by their (likely shared) offending value."""
    groups: dict[object, list[ErrorDetails]] = {}
    for err in errors:
        groups.setdefault(_group_key(err), []).append(err)
    return list(groups.values())


def _print_msg(console: rich.console.Console, err: ErrorDetails) -> None:
    """Print a pydantic sub-error's type/message. May be one of several for the same field."""
    console.print(f"    {err['type']}: {err['msg']}", markup=False)


def _print_input(
    console: rich.console.Console, entry_root: Path, value: object
) -> None:
    """Print an input value's type/repr, plus a source snippet when available."""
    console.print(f"    input ({type(value).__name__}): {value!r}", markup=False)
    _print_input_snippet(console, entry_root, value)


def _print_input_snippet(
    console: rich.console.Console, entry_root: Path, value: object
) -> None:
    """Show a few lines of source around a value's position, if it has one."""
    if not isinstance(value, Positioned) or value.__position__.is_synthetic:
        return
    pos = value.__position__
    try:
        code = (entry_root / pos.path).read_text()
    except OSError:
        return
    lo = max(1, pos.start.line - 5)
    hi = pos.end.line + 5
    syntax = Syntax(
        code,
        "yaml",
        line_numbers=True,
        line_range=(lo, hi),
        highlight_lines=set(range(pos.start.line, pos.end.line + 1)),
    )
    console.print(
        Panel(
            syntax,
            title=f"{pos.path}:{pos.start.line}:{pos.start.column}",
            title_align="left",
            border_style="dim",
            padding=(0, 1),
        )
    )


def _print_exc(
    console: rich.console.Console, entry_root: Path, exc: BaseException
) -> None:
    """Print an exception's error message(s) and, if possible, the offending source. No traceback."""
    if isinstance(exc, ValidationError):
        for group in _group_errors(exc.errors()):
            heading = min(group, key=lambda e: len(e["loc"]))
            console.print(f"  [bold]{_loc_str(exc, heading['loc'])}[/bold]")
            for err in group:
                _print_msg(console, err)
            _print_input(console, entry_root, group[0]["input"])  # pyright: ignore[reportAny]
    else:
        console.print(f"  {type(exc).__name__}: {exc}", markup=False)


def _rule_label(field_pat: re.Pattern[str], msg_pat: re.Pattern[str]) -> str:
    """Human-readable label for an IGNORED_ERRORS rule, used as its counter key."""
    return f"{field_pat.pattern!r} / {msg_pat.pattern!r}"


def _is_ignored(location: str, exc: Exception, ignore_counts: Counter[str]) -> bool:
    """Whether an exception raised/recorded during extraction should be ignored.

    Parsing errors are always genuine dataset issues, not AST bugs, and are
    always ignored. A ValidationError is ignored only if every one of its
    sub-errors is part of a group (see `_group_errors`) matched by an entry in
    `IGNORED_ERRORS` — a rule matches a group if its field-path regex hits any
    member's loc and its message regex hits any member's message. Each
    matching rule's trigger count is tallied in `ignore_counts`, so rules that
    fire too often (a sign of an overly broad ignore) can be spotted in the
    final report.
    """
    if location in IGNORED_LOCATIONS:
        return True
    if isinstance(exc, YAMLError):
        ignore_counts[PARSING_ERROR_LABEL] += 1
        return True
    if not isinstance(exc, ValidationError):
        return False

    errors = exc.errors()
    if not errors:
        return False

    matched_labels: list[str] = []
    for group in _group_errors(errors):
        label = next(
            (
                _rule_label(field_pat, msg_pat)
                for field_pat, msg_pat in RE_IGNORED_ERRORS
                if any(field_pat.search(_loc_str(exc, e["loc"])) for e in group)
                and any(msg_pat.search(_err_str(e)) for e in group)
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
            try:
                tf.extractall(tmp, filter="data")
            except tarfile.LinkOutsideDestinationError:
                raise FileNotFoundError(f"Bad archive {archive} with symlink")
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
            if repo in (
                "redhat-cop/agnosticd",
                "redhat-cip/rcip-openshift-ansible",
                "redhat-cop/controller_configuration",
            ):
                # These repos is very broken, with tonnes of incorrect syntax.
                progress.advance(task_id, len(repo_entrypoints))
                continue

            try:
                with _resolve_repo(data_dir, repo) as repo_dir:
                    for entrypoint in repo_entrypoints:
                        progress.advance(task_id)
                        entrypoint_path = repo_dir / entrypoint["relative_path"]
                        entry_root = (
                            entrypoint_path.parent
                            if entrypoint["type"] == "playbook"
                            else entrypoint_path
                        )
                        location = f"{repo}/{entrypoint['relative_path']}"
                        progress.update(task_id, description=location)

                        try:
                            result = _extract(entrypoint_path, entrypoint["type"])
                        except Exception as exc:
                            if _is_ignored(location, exc, ignore_counts):
                                ignored_count += 1
                                continue
                            error_console.rule(style="red")
                            error_console.print(f"[bold red]{location}[/bold red]")
                            _print_exc(error_console, entry_root, exc)
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

                            error_console.rule(style="red")
                            error_console.print(f"[bold red]{location}[/bold red]")
                            _print_exc(error_console, entry_root, b.reason)
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
