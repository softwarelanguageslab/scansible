# pyright: reportUnknownVariableType = false

"""Shared types used across the AST representation."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from scansible.cst import YamlValue

from ._validators import RelativePath

#: Raw dictionaries of Ansible entities.
type RawDirectives = dict[str, YamlValue]


class ExtractionContext:
    """Context during extraction, to store broken files etc."""

    #: Whether extraction should be lenient. If true, the extractor will skip
    #: tasks or blocks that fail to extract, without skipping the entire file.
    #: If false, the entire file will be skipped instead.
    lenient: bool
    #: List of broken files which could not be parsed/extracted.
    broken_files: list[BrokenFile]
    #: List of broken tasks or blocks that could not be parsed/extracted.
    broken_tasks: list[BrokenTask]

    def __init__(self, *, lenient: bool) -> None:
        self.lenient = lenient
        self.broken_files = []
        self.broken_tasks = []


class BrokenTask(BaseModel, frozen=True, arbitrary_types_allowed=True):
    """Represents a task/block that could not be extracted."""

    #: The raw datastructure that failed to extract.
    raw: object
    #: The reason for failure.
    reason: ValidationError


class BrokenFile(BaseModel, frozen=True, arbitrary_types_allowed=True):
    """Represents a file that could not be parsed or extracted."""

    #: The relative path to the file in the project.
    path: RelativePath
    #: The reason for failure.
    reason: Exception


__all__ = [
    "ExtractionContext",
    "BrokenTask",
    "BrokenFile",
]
