from __future__ import annotations

from typing import TYPE_CHECKING

import rich

from scansible.representations.pdg.representation import NodeLocation

if TYPE_CHECKING:
    from . import CheckResult


class TerminalReporter:
    def report_results(self, results: list[CheckResult]) -> None:
        if not results:
            rich.print("[green]No warnings found, keep it up!")
        for name, loc in sorted(set(results), key=lambda p: str(p[1])):
            if isinstance(loc, str):
                rich.print(f"[gray]{loc}[/gray] - [bold red]{name}[/bold red]")
            else:
                rich.print(
                    f"[gray]{loc.file}:{loc.line}:{loc.column}[/gray] - [bold red]{name}[/bold red]"
                )
                if loc.includer_location is not None:
                    self.print_includer_loc(loc.includer_location)

    def print_includer_loc(self, loc: NodeLocation) -> None:
        rich.print(f"\t[gray]via {loc.file}:{loc.line}:{loc.column}")
        if loc.includer_location is not None:
            self.print_includer_loc(loc.includer_location)
