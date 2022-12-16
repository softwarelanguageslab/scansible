from __future__ import annotations

import rich

class TerminalReporter:
    def report_results(self, results: list[tuple[str, str, str, int]]) -> None:
        if not results:
            rich.print('[green]No warnings found, keep it up!')
        for name, loc, _, _ in sorted(set(results), key=lambda p: p[1]):
            rich.print(f'[gray]{loc}[/gray] - [bold red]{name}[/bold red]')
