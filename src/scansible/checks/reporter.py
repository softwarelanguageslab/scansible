from __future__ import annotations

from typing import TYPE_CHECKING

import rich

from scansible.pdg.representation import NodeLocation

if TYPE_CHECKING:
    from .base import Finding


class TerminalReporter:
    def report_results(self, results: list[Finding]) -> None:
        console = rich.console.Console(width=999)
        if not results:
            console.print("[green]No warnings found, keep it up!")
        for finding in sorted(set(results), key=lambda f: str(f.location)):
            loc = finding.location
            label = f"[bold red][{finding.code}][/bold red] {finding.summary}"
            if loc.is_synthetic:
                console.print(label, width=999)
            else:
                console.print(
                    f"[gray]{loc.path}:{loc.start.line}:{loc.start.column}[/gray] - {label}",
                    width=999,
                )
                if loc.includer_location is not None:
                    self.print_includer_loc(loc.includer_location, console)

    def print_includer_loc(
        self, loc: NodeLocation, console: rich.console.Console
    ) -> None:
        console.print(f"\t[gray]via {loc.path}:{loc.start.line}:{loc.start.column}")
        if loc.includer_location is not None:
            self.print_includer_loc(loc.includer_location, console)
