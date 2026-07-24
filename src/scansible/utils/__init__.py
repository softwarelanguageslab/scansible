"""Utilities used throughout Scansible."""

from __future__ import annotations

from typing import override

import io
from collections.abc import Generator
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout

from .collections import FrozenDict as FrozenDict
from .collections import ensure_sequence as ensure_sequence
from .collections import first as first
from .collections import first_where as first_where
from .collections import join_sequences as join_sequences
from .collections import make_immutable as make_immutable
from .files import ProjectPath as ProjectPath
from .files import SourceFileMap as SourceFileMap
from .files import find_all_files as find_all_files
from .files import find_file as find_file
from .position import LineColumn as LineColumn
from .position import Position as Position
from .position import Positioned as Positioned


class Sentinel:
    @override
    def __repr__(self) -> str:
        return "SENTINEL"


SENTINEL = Sentinel()


@contextmanager
def capture_output() -> Generator[io.StringIO]:
    r"""Context manager which, while active, captures all printed output.

    Useful to capture Ansible logs that otherwise get printed to the terminal.
    The captured output will be available as the variable in the `with`
    statement.

    Example:
        ```python
        with capture_output() as output:
            print("hello world")
            sys.stderr.write("test\n")
        output.getvalue()  # "hello world\ntest\n"
        ```
    """
    buffer = io.StringIO()
    with ExitStack() as stack:
        _ = stack.enter_context(redirect_stderr(buffer))
        _ = stack.enter_context(redirect_stdout(buffer))
        yield buffer
