from __future__ import annotations

from typing import TextIO

import sys
from collections.abc import Sequence
from pathlib import Path

import click
from ansible import constants as ans_constants
from loguru import logger


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
) -> None:
    """Build a PDG for a project residing at PROJECT_PATH."""
    if name is None:
        name = project_path.name
    as_pb = None if project_type is None else project_type == "playbook"
    role_search_paths = list(role_search_path) + [
        Path(p) for p in ans_constants.DEFAULT_ROLES_PATH
    ]

    from .representations.pdg import dump_graph, extract_pdg

    ctx = extract_pdg(
        project_path, name, version, role_search_paths, as_pb=as_pb, lenient=not strict
    )
    logger.info(
        f"Extracted PDG of {len(ctx.graph)} nodes and {len(ctx.graph.edges())} edges"
    )
    output.write(dump_graph(output_format, ctx.graph))

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


if __name__ == "__main__":
    cli()
