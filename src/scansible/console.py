"""Shared terminal output setup."""

from __future__ import annotations

import sys

import rich.console
from loguru import logger


def make_console(**kwargs: object) -> rich.console.Console:
    """Construct a `Console` with Scansible's defaults.

    Disables Rich's automatic repr-highlighting (which auto-colours
    things that look like numbers, paths, UUIDs, etc. in any plain
    string passed to `print`), so the only colour in the output is
    what we explicitly ask for.
    """
    _ = kwargs.setdefault("highlight", False)
    return rich.console.Console(**kwargs)  # pyright: ignore[reportArgumentType]


#: Console for primary output.
console = make_console()
#: Console for warnings/errors printed outside the main result stream.
error_console = make_console(stderr=True)


def configure_logging(level: str) -> None:
    """(Re)configure the `loguru` sink used for build/check logging."""
    logger.remove()
    _ = logger.add(
        sys.stderr,
        level=level,
        format="<level>{level: <8}</level> {message}",
    )
