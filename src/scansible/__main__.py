from __future__ import annotations

from typing import TextIO

import csv
import sys
from collections.abc import Sequence
from pathlib import Path

import click
import rich.console
import rich.progress
from ansible import constants as ans_constants
from loguru import logger

from scansible.representations.pdg.canonical import canonicalize_pdg
from scansible.utils.module_type_info import ModuleKnowledgeBase


@click.group
@click.option("-v", "--verbose", is_flag=True, default=False, help="Print debug output")
@click.option(
    "-q", "--quiet", is_flag=True, default=False, help="Print only warnings and errors"
)
def cli(verbose: bool, quiet: bool) -> None:
    """Static Code Analysis for Ansible."""
    if verbose and quiet:
        raise click.BadOptionUsage(
            "verbose", "--verbose and --quiet are mutually exclusive"
        )
    # Set up logging
    logger.remove()
    desired_level = "DEBUG" if verbose else "WARNING" if quiet else "INFO"
    logger.add(sys.stderr, level=desired_level)


@cli.command
@click.argument(
    "project_path", type=click.Path(exists=True, resolve_path=True, path_type=Path)
)
@click.option(
    "-o",
    "--output",
    type=click.File(mode="wt"),
    default="-",
    help="File to write output to, defaults to stdout",
)
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["graphml", "neo4j", "graphviz"]),
    default="graphml",
    help="Output format (default: graphml)",
)
@click.option(
    "-t",
    "--type",
    "project_type",
    type=click.Choice(["playbook", "role"]),
    help="Type of the provided project (default: autodetect)",
)
@click.option(
    "--role-search-path",
    type=click.Path(file_okay=False, path_type=Path),
    envvar="ROLE_SEARCH_PATH",
    multiple=True,
    help='Additional search paths to find role dependencies. Can be specified as environment variable "ROLE_SEARCH_PATH" (multiple paths can be separated with ":"). Provided directories are prepended to Ansible defaults.',
)
@click.option("--name", type=str, help="Project name (default: name of project path)")
@click.option(
    "--version", type=str, default="latest", help='Project version (default: "latest"")'
)
@click.option(
    "--aux",
    "aux_file",
    type=click.File(mode="wt"),
    help="File to write auxiliary information to (default: not written)",
)
@click.option(
    "--errors",
    "errors_file",
    type=click.File(mode="wt"),
    help="File to write error log to (default: not written)",
)
@click.option(
    "--strict/--lenient",
    default=False,
    help="Whether extraction and building should be strict. This aborts processing files if a single task in that file is malformed. (default: lenient)",
)
@click.option(
    "--canonicalize/--no-canonicalize",
    default=False,
    help="Whether to canonicalize the resulting graph",
)
@click.option(
    "--module-kb-path",
    type=click.Path(resolve_path=True, path_type=Path, dir_okay=False, exists=True),
    help="Path to the module knowledge base (only required when --canonicalize is set)",
)
@click.option(
    "--transitive-cfg/--no-transitive-cfg",
    default=False,
    help="Whether to construct a transitive closure over the CFG.",
)
def build_pdg(
    project_path: Path,
    name: str | None,
    version: str,
    role_search_path: Sequence[Path],
    output: TextIO,
    output_format: str,
    project_type: str | None,
    aux_file: TextIO | None,
    errors_file: TextIO | None,
    strict: bool,
    canonicalize: bool,
    module_kb_path: Path | None,
    transitive_cfg: bool,
) -> None:
    """Build a PDG for a project residing at PROJECT_PATH."""
    if name is None:
        name = project_path.name
    as_pb = None if project_type is None else project_type == "playbook"
    role_search_paths = list(role_search_path) + [
        Path(p) for p in ans_constants.DEFAULT_ROLES_PATH
    ]

    if canonicalize and not module_kb_path:
        raise ValueError("--module-kb-path is required when --canonicalize is set")

    from .representations.pdg import dump_graph, extract_pdg

    ctx = extract_pdg(
        project_path,
        name,
        version,
        role_search_paths,
        as_pb=as_pb,
        lenient=not strict,
        construct_transitive_cfg=transitive_cfg,
    )
    pdg = ctx.graph
    logger.info(f"Extracted PDG of {len(pdg)} nodes and {len(pdg.edges())} edges")

    if canonicalize:
        assert module_kb_path
        pdg = canonicalize_pdg(pdg, ModuleKnowledgeBase.load_from_file(module_kb_path))
        logger.info(f"Reduced size to {len(pdg)} nodes and {len(pdg.edges())} edges")

    output.write(dump_graph(output_format, pdg))

    if aux_file is not None:
        aux_file.write(ctx.visibility_information.dump())
    if errors_file is not None:
        errors_file.write(ctx.summarise_extraction_errors())


@cli.command
@click.argument(
    "project_path", type=click.Path(exists=True, resolve_path=True, path_type=Path)
)
@click.option(
    "-t",
    "--type",
    "project_type",
    type=click.Choice(["playbook", "role"]),
    help="Type of the provided project (default: autodetect)",
)
@click.option("--db-host", help="DB host", envvar="DB_HOST")
@click.option(
    "--role-search-path",
    type=click.Path(file_okay=False, path_type=Path),
    envvar="ROLE_SEARCH_PATH",
    multiple=True,
    help='Additional search paths to find role dependencies. Can be specified as environment variable "ROLE_SEARCH_PATH" (multiple paths can be separated with ":"). Provided directories are prepended to Ansible defaults.',
)
@click.option(
    "--strict/--lenient",
    default=False,
    help="Whether extraction and building should be strict. This aborts processing files if a single task in that file is malformed. (default: lenient)",
)
@click.option(
    "--enable-security/--skip-security",
    default=True,
    help="Whether to enable security smells",
)
@click.option(
    "--enable-semantics/--skip-semantics",
    default=True,
    help="Whether to enable semantic smells",
)
def check(
    project_path: Path,
    role_search_path: Sequence[Path],
    project_type: str | None,
    strict: bool,
    enable_security: bool,
    enable_semantics: bool,
    db_host: str,
) -> None:
    """Check the project residing at PROJECT_PATH for smells."""
    name = project_path.name
    as_pb = None if project_type is None else project_type == "playbook"
    role_search_paths = list(role_search_path) + [
        Path(p) for p in ans_constants.DEFAULT_ROLES_PATH
    ]

    from .representations.pdg import extract_pdg

    ctx = extract_pdg(
        project_path, name, "latest", role_search_paths, as_pb=as_pb, lenient=not strict
    )

    from .checks import TerminalReporter, run_all_checks

    reporter = TerminalReporter()
    results = run_all_checks(
        ctx,
        db_host,
        enable_security=enable_security,
        enable_semantics=enable_semantics,
    )
    reporter.report_results(results)


@cli.command
@click.argument(
    "project_path", type=click.Path(exists=True, resolve_path=True, path_type=Path)
)
@click.argument(
    "file_path", type=click.Path(exists=True, resolve_path=True, path_type=Path)
)
@click.option(
    "-t",
    "--type",
    "project_type",
    type=click.Choice(["playbook", "role"]),
    help="Type of the provided project (default: autodetect)",
)
@click.option("--db-host", help="DB host", envvar="DB_HOST")
@click.option(
    "--role-search-path",
    type=click.Path(file_okay=False, path_type=Path),
    envvar="ROLE_SEARCH_PATH",
    multiple=True,
    help='Additional search paths to find role dependencies. Can be specified as environment variable "ROLE_SEARCH_PATH" (multiple paths can be separated with ":"). Provided directories are prepended to Ansible defaults.',
)
@click.option(
    "--strict/--lenient",
    default=False,
    help="Whether extraction and building should be strict. This aborts processing files if a single task in that file is malformed. (default: lenient)",
)
@click.option(
    "--enable-security/--skip-security",
    default=True,
    help="Whether to enable security smells",
)
@click.option(
    "--enable-semantics/--skip-semantics",
    default=True,
    help="Whether to enable semantic smells",
)
def check_all(
    project_path: Path,
    file_path: Path,
    role_search_path: Sequence[Path],
    project_type: str | None,
    strict: bool,
    enable_security: bool,
    enable_semantics: bool,
    db_host: str,
) -> None:
    """Check the project residing at PROJECT_PATH for smells in all files."""
    name = project_path.name
    role_search_paths = list(role_search_path) + [
        Path(p) for p in ans_constants.DEFAULT_ROLES_PATH
    ]

    from .representations.pdg import extract_pdg
    from .utils.entrypoints import find_entrypoints
    entrypoints = find_entrypoints(project_path)
    results = []
    logger.remove()

    for entrypoint, project_type in entrypoints:
        as_pb = None if project_type is None else project_type == "playbook"
        ctx = extract_pdg(
            entrypoint, name, "latest", role_search_paths, as_pb=as_pb, lenient=not strict
        )

        from .checks import TerminalReporter, run_all_checks

        results.extend(run_all_checks(
            ctx,
            db_host,
            enable_security=enable_security,
            enable_semantics=enable_semantics,
        ))

    reporter = TerminalReporter()
    reporter.report_results([
        result
        for result in results
        if result.location.split(':')[0] == str(file_path)
    ])


@cli.command()
@click.argument("output_path", type=click.Path(resolve_path=True, path_type=Path))
@click.argument(
    "ansible_doc_path",
    default="ansible-doc",
    type=click.Path(
        resolve_path=True, exists=True, dir_okay=False, executable=True, path_type=Path
    ),
)
@click.option(
    "--full",
    type=bool,
    help="Include descriptions, examples, etc. in the dumped output",
    default=False,
)
def prepare_module_kb(
    output_path: Path, ansible_doc_path: Path, full: bool = False
) -> None:
    """Prepare the knowledge base of modules and write it to OUTPUT_PATH."""

    kb = ModuleKnowledgeBase.init_from_ansible_docs(str(ansible_doc_path))
    output_path.parent.mkdir(exist_ok=True, parents=True)
    kb.dump_to_file(output_path, slim=not full)


@cli.command()
@click.argument("input_file", type=click.File())
@click.argument(
    "repo_dir",
    type=click.Path(resolve_path=True, path_type=Path, exists=True, file_okay=False),
)
@click.argument(
    "output_path", type=click.Path(resolve_path=True, path_type=Path, file_okay=False)
)
@click.option(
    "--role-search-path",
    type=click.Path(file_okay=False, path_type=Path),
    envvar="ROLE_SEARCH_PATH",
    multiple=True,
    help='Additional search paths to find role dependencies. Can be specified as environment variable "ROLE_SEARCH_PATH" (multiple paths can be separated with ":"). Provided directories are prepended to Ansible defaults.',
)
@click.option(
    "--canonicalize/--no-canonicalize",
    default=False,
    help="Whether to canonicalize the resulting graph",
)
@click.option(
    "--module-kb-path",
    type=click.Path(resolve_path=True, path_type=Path, dir_okay=False, exists=True),
    help="Path to the module knowledge base (only required when --canonicalize is set)",
)
@click.option(
    "--transitive-cfg/--no-transitive-cfg",
    default=False,
    help="Whether to construct a transitive closure over the CFG.",
)
def bulk_build(
    input_file: TextIO,
    repo_dir: Path,
    output_path: Path,
    role_search_path: Sequence[Path],
    canonicalize: bool,
    module_kb_path: Path | None,
    transitive_cfg: bool,
) -> None:
    """Build a collection of PDGs in bulk.

    Input entrypoint paths are read from INPUT_FILE, which should be a CSV containing
    fields `repo`, `relative_path`, `type`.
    Resulting PDGs are stored in GraphML format in OUTPUT_PATH, which should be
    a directory and will be created if it does not exist. Each entrypoint will
    be extracted separately.
    """

    if canonicalize and not module_kb_path:
        raise ValueError("--module-kb-path is required when --canonicalize is set")

    entrypoints = list(csv.DictReader(input_file))
    output_path.mkdir(exist_ok=True, parents=True)

    if canonicalize:
        assert module_kb_path
        module_kb = ModuleKnowledgeBase.load_from_file(module_kb_path)

    from .representations.pdg import dump_graph, extract_pdg

    with (output_path / "failed.csv").open("wt") as failed_out_f, (
        output_path / "errors.log"
    ).open("wt") as error_log_f:
        failed_out_csv = csv.DictWriter(
            failed_out_f, fieldnames=["repo", "relative_path", "type"]
        )
        failed_out_csv.writeheader()
        error_console = rich.console.Console(file=error_log_f)

        for entrypoint in rich.progress.track(
            entrypoints, description=f"Building PDGs for {len(entrypoints)} entrypoints"
        ):
            repo_path = repo_dir / entrypoint["repo"]
            entrypoint_path = repo_path / entrypoint["relative_path"]
            output_base = output_path / f"{repo_path.parent.name}"
            output_name = "-".join(entrypoint_path.relative_to(repo_path.parent).parts)

            log_path = output_base / f"{output_name}.log"
            log_path.unlink(missing_ok=True)
            logger.remove()
            logger.add(log_path, level="INFO")
            try:
                ctx = extract_pdg(
                    entrypoint_path,
                    entrypoint_path.name,
                    "latest",
                    role_search_paths=role_search_path,
                    lenient=True,
                    as_pb=entrypoint["type"] == "playbook",
                    construct_transitive_cfg=transitive_cfg,
                )
                pdg = ctx.graph
                logger.info(
                    f"Extracted PDG of {len(pdg)} nodes and {len(pdg.edges())} edges"
                )

                if canonicalize:
                    pdg = canonicalize_pdg(pdg, module_kb)  # pyright: ignore
                    logger.info(
                        f"Reduced size to {len(pdg)} nodes and {len(pdg.edges())} edges"
                    )
            except Exception as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise

                error_console.rule(str(exc))
                error_console.print_exception(max_frames=5)
                error_console.print(entrypoint_path)
                failed_out_csv.writerow(entrypoint)
                failed_out_f.flush()

                continue

            (output_base / f"{output_name}.xml").write_text(dump_graph("graphml", pdg))


if __name__ == "__main__":
    cli()
