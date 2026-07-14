"""Helpers for structural model extraction."""

from __future__ import annotations

from typing import NoReturn, Protocol, override

import io
import os.path
from collections.abc import Generator
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from . import ansible_types as ans


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
    loader = ans.DataLoader()
    return loader.load_from_file(str(path.absolute))


def find_file(dir_path: ProjectPath, file_name: str) -> ProjectPath | None:
    """
    Find a YAML file in a project directory, regardless of file extension.

    :raises     AssertionError:  When multiple files were found.
    """
    # TODO: Use `SourceFileMap`?
    loader = ans.DataLoader()
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
        if child.is_file() and child.suffix in ans.C.YAML_FILENAME_EXTENSIONS:
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


class _Intercepter(Protocol):
    def __call__(self, *_args: object, **_kwargs: object) -> NoReturn: ...


@contextmanager
def prevent_undesired_operations() -> Generator[None]:
    """
    Context manager which, while active, blocks Ansible from performing
    undesired operations such as evaluating template expressions or eagerly
    loading included files.
    """
    from ansible.playbook import helpers
    from ansible.template import Templar

    old_load_list_of_tasks = helpers.load_list_of_tasks
    old_templar_do_template = Templar.do_template
    old_templar_template = Templar.template

    def raise_if_called(name: str) -> _Intercepter:
        def raiser(*_args: object, **_kwargs: object) -> NoReturn:
            raise FatalError(f"{name} was called when it was not supposed to be called")

        return raiser

    helpers.load_list_of_tasks = raise_if_called("load_list_of_tasks")
    Templar.do_template = raise_if_called("Templar.do_template")
    Templar.template = raise_if_called("Templar.template")

    try:
        yield
    finally:
        helpers.load_list_of_tasks = old_load_list_of_tasks
        Templar.do_template = old_templar_do_template
        Templar.template = old_templar_template
