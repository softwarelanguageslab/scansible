"""Utilities related to file systems and project directories."""

from __future__ import annotations

from typing import override

import os
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path

from loguru import logger

from scansible.constants import YAML_EXTENSIONS

from .collections import FrozenDict


class SourceFileMap[FileType](Mapping[str, FileType]):
    """A collection of source files of a certain type, supporting stem-based indexing.

    This provides a convenient API to find source files without needing to take the concrete
    extension (.yml, .yaml, or .json) into account.

    Can optionally be given a search prefix. When provided, each lookup will attempt to resolve
    a prefixed file name, and fall back to unprefixed search later. This can be useful when all
    files in the map are in the same root directory. For instance, a file map for role task files
    can use "tasks/" as a prefix, allowing individual task files to be accessed without prefixing
    "tasks/" in the lookup.
    """

    def __init__(
        self, file_list: Iterable[tuple[str, FileType]], *, prefix: str = ""
    ) -> None:
        self._mapping: Mapping[str, FileType] = FrozenDict(file_list)
        # If prefix is given, prioritise with the prefix but try without the prefix afterwards.
        self._prefixes: Sequence[str] = (prefix, "") if prefix else ("",)

    @override
    def __getitem__(self, key: str) -> FileType:
        for prefix in self._prefixes:
            for ext in (".yml", ".yaml", ".json", ""):
                file_name = f"{prefix}{key}{ext}"
                if file_name in self._mapping:
                    return self._mapping[file_name]

        raise KeyError(f"No file named {key}")

    @override
    def __len__(self) -> int:
        return len(self._mapping)

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)


class ProjectPath:
    """Represents a path in a project.

    Stores the project root path and the relative path to a file or
    directory in the project.
    """

    #: The project's root path. Must be a directory.
    root: Path
    #: Path to the content, relative to the root path.
    relative: Path

    def __init__(self, root_path: Path, file_path: Path | str) -> None:
        if not root_path.is_absolute() or not root_path.is_dir():
            raise ValueError("Root path must be absolute path to existing directory")
        self.root = root_path.resolve()

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if file_path.is_absolute():
            relative = Path(os.path.relpath(file_path, root_path))
        else:
            relative = file_path

        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError(f"Path {file_path} escapes project root {self.root}")
        self.relative = relative

    @override
    def __str__(self) -> str:
        return str(self.absolute)

    @classmethod
    def from_root(cls, root_path: Path) -> ProjectPath:
        """Construct a ProjectPath instance for the project root.

        If given a file, will set the root to the parent of the file.

        :param root_path: The root path to the project.
        """
        if root_path.is_file():
            return cls(root_path.parent, root_path.name)
        return cls(root_path, ".")

    def join(self, other: Path | str) -> ProjectPath:
        """Join the current path with another path.

        :raises ValueError: When the resulting path escapes the project root.
        """
        if isinstance(other, str):
            other = Path(other)

        return ProjectPath(self.root, self.relative / other)

    @property
    def absolute(self) -> Path:
        """The absolute path to the content."""
        return (self.root / self.relative).resolve()


def find_file(dir_path: ProjectPath, file_name: str) -> ProjectPath | None:
    """Find a YAML file in a project directory, regardless of file extension.

    :raises AssertionError: When multiple files were found.
    """
    candidates = [f"{file_name}{ext}" for ext in ["", *YAML_EXTENSIONS]]
    for candidate in candidates:
        if (dir_path.absolute / candidate).is_file():
            return dir_path.join(candidate)

    return None


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
                # TODO: Why can this spin in an infinite loop??
                logger.warning(f"Hit recursion limit while walking {child}")

    return results
