"""Helpers for structural model extraction."""

from __future__ import annotations

from typing import override

import io
import os.path
from collections.abc import Generator
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from ansible.parsing.dataloader import DataLoader


class FatalError(Exception):
    """Fatal error to stop all extraction."""

    pass


class ProjectPath:
    """
    Represents a path in a project, storing the project root path and the
    relative path to a file or directory in the project.
    """

    #: The project's root path. Must be a directory.
    root: Path
    #: Path to the content, relative to the root path.
    relative: Path

    def __init__(self, root_path: Path, file_path: Path | str) -> None:
        assert root_path.is_absolute()
        assert root_path.is_dir()
        self.root = root_path

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if file_path.is_absolute():
            self.relative = Path(os.path.relpath(file_path, root_path))
        else:
            self.relative = file_path

    @override
    def __str__(self) -> str:
        return str(self.absolute)

    @classmethod
    def from_root(cls, root_path: Path) -> ProjectPath:
        """
        Construct a ProjectPath instance for the project root.
        If given a file, will set the root the the parent of the file.

        :param      root_path:  The root path to the project.
        :type       root_path:  Path
        """
        if root_path.is_file():
            return cls(root_path.parent, root_path.name)
        return cls(root_path, ".")

    def join(self, other: Path | str) -> ProjectPath:
        """
        Join the current path with another path.

        :raises     AssertionError:  When the two project paths have different roots.
        """
        if isinstance(other, str):
            other = Path(other)

        return ProjectPath(self.root, self.relative / other)

    @property
    def absolute(self) -> Path:
        """The absolute path to the content."""
        return (self.root / self.relative).resolve()


def parse_file(path: ProjectPath) -> object:
    """Parse a YAML file using Ansible's parser."""
    loader = DataLoader()
    return loader.load_from_file(str(path.absolute))


def find_file(dir_path: ProjectPath, file_name: str) -> ProjectPath | None:
    """
    Find a YAML file in a project directory, regardless of file extension.

    :raises     AssertionError:  When multiple files were found.
    """
    # TODO: Use `SourceFileMap`?
    loader = DataLoader()
    # DataLoader.find_vars_files is misnamed.
    found_paths = loader.find_vars_files(
        str(dir_path.absolute), file_name, allow_dir=False
    )
    # found_paths should always have at most one element, since it can only have
    # multiple elements when allow_dir=True

    if not found_paths:
        return None

    found_path = found_paths[0]
    return dir_path.join(
        found_path.decode("utf-8") if isinstance(found_path, bytes) else found_path
    )


def find_all_files(dir_path: ProjectPath) -> list[ProjectPath]:
    """Recursively find all YAML files in a project directory."""
    results: list[ProjectPath] = []
    for child in dir_path.absolute.iterdir():
        child_path = dir_path.join(child)
        if child.is_symlink():
            continue
        if child.is_file() and child.suffix in (".yml", ".yaml", ".json"):
            results.append(child_path)
        elif child.is_dir():
            try:
                results.extend(find_all_files(child_path))
            except RecursionError:
                print(child)
                # TODO: Why can this spin in an infinite loop??
                pass

    return results


@contextmanager
def capture_output() -> Generator[io.StringIO]:
    """Context manager which, while active, captures all printed output.

    Useful to capture Ansible logs that otherwise get printed to the terminal.
    The captured output will be available as the variable in the `with`
    statement.

    Example:
      with capture_output() as output:
        print("hello world")
        sys.stderr.write('test\n')
      output.getvalue()  # hello world\ntest\n
    """
    buffer = io.StringIO()
    with ExitStack() as stack:
        _ = stack.enter_context(redirect_stderr(buffer))
        _ = stack.enter_context(redirect_stdout(buffer))
        yield buffer
