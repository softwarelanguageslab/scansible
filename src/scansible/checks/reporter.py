from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path

from rich.markup import escape
from rich.text import Text

from scansible.console import console

if TYPE_CHECKING:
    from scansible.pdg.representation import NodeLocation

    from .base import Finding


class TerminalReporter:
    """Renders `Finding`s in a user-friendly format.

    The format is inspired by the output of the ruff linter:
    code, message, a `-->` location line, and a source code frame
    with carets under the span.
    """

    def __init__(self, project_root: Path) -> None:
        #: Root that `Location.path` values are resolved against to read source for the code frame.
        self._project_root: Path = project_root

    def report_results(self, results: list[Finding]) -> None:
        findings = sorted(set(results), key=lambda f: str(f.location))

        for finding in findings:
            self._print_finding(finding)

        self._print_summary(len(findings))

    def _print_summary(self, count: int) -> None:
        if count == 0:
            console.print("[bold green]✓ All checks passed![/bold green]")
            return

        noun = "error" if count == 1 else "errors"
        console.print(f"[bold red]Found {count} {noun}.[/bold red]")

    def _print_finding(self, finding: Finding) -> None:
        console.print(f"[bold red]{finding.code}[/bold red] {escape(finding.summary)}")
        self._print_location(finding.location)

        if finding.hint_location is not None:
            console.print(f"note: {escape(finding.hint_text)}")
            self._print_location(finding.hint_location)

        if finding.explanation:
            console.print(f"note: {escape(finding.explanation)}")

        includer = finding.location.includer_location
        while includer is not None:
            loc_str = f"{includer.path}:{includer.start.line}:{includer.start.column}"
            console.print(f"note: included via {escape(loc_str)}")
            includer = includer.includer_location

        console.print()

    def _print_location(self, location: NodeLocation) -> None:
        if location.is_synthetic:
            return

        loc_str = f"{location.path}:{location.start.line}:{location.start.column}"
        console.print(f"[cyan] -->[/cyan] {escape(loc_str)}")

        for row in self._build_frame(location):
            console.print(row)

    def _build_frame(self, location: NodeLocation) -> list[Text]:
        # If the file can't be found or read relative to the project root,
        # degrade gracefully to no code frame.
        try:
            source_lines = (self._project_root / location.path).read_text().splitlines()
        except OSError:
            return []

        start_line, start_col = location.start
        end_line, end_col = location.end
        if not (1 <= start_line <= len(source_lines)):
            return []

        shown_lines = [start_line - 1, start_line] if start_line > 1 else [start_line]

        gutter_width = len(str(start_line))
        blank_gutter = Text(" " * gutter_width + " |", style="dim")

        rows = [blank_gutter]
        for lineno in shown_lines:
            source = source_lines[lineno - 1]
            row = Text(f"{lineno:>{gutter_width}} | ", style="dim")
            _ = row.append(source)
            rows.append(row)

            if lineno == start_line:
                rows.append(
                    self._build_caret_row(
                        gutter_width, source, start_line, start_col, end_line, end_col
                    )
                )

        rows.append(blank_gutter)
        return rows

    def _build_caret_row(
        self,
        gutter_width: int,
        source: str,
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
    ) -> Text:
        # `end` is exclusive, so the span is `end_col - start_col` columns wide.
        # For a span crossing multiple lines, only underline from the
        # start column to the end of this (first) line.
        if end_line == start_line and end_col > start_col:
            caret_count = end_col - start_col
        else:
            caret_count = max(1, len(source) - start_col + 1)

        row = Text(" " * gutter_width + " | ", style="dim")
        _ = row.append(" " * (start_col - 1))
        _ = row.append("^" * caret_count, style="bold red")
        return row
