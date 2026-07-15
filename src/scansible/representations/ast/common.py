# pyright: reportUnknownVariableType = false

"""Shared types used across the AST representation."""

from __future__ import annotations

from typing import Annotated, cast

from pathlib import Path

from ansible.parsing.dataloader import DataLoader
from pydantic import (
    BaseModel,
    PositiveInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from scansible.types import AnyValue
from scansible.utils import ProjectPath

from ._validators import RelativePath


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

    def __init__(self, lenient: bool) -> None:
        self.lenient = lenient
        self.broken_files = []
        self.broken_tasks = []


#: Raw Ansible position tuple, with validation logic.
type RawPosition = tuple[
    Annotated[str, StringConstraints(strict=True, min_length=1)],
    PositiveInt,
    PositiveInt,
]

RawPositionAdapter = TypeAdapter(RawPosition)

#: Raw dictionaries of Ansible entities.
type RawDirectives = dict[str, AnyValue]


class Position(BaseModel, strict=True, frozen=True, extra="forbid"):
    """Code position of an AST node."""

    # TODO: Should this be a RelativePath instead?
    #: Path to the file containing the node.
    file: Path = Path("unknown file")
    #: Line number, 1-indexed.
    start_line: PositiveInt = -1
    #: Column number, 1-indexed.
    start_column: PositiveInt = -1

    @property
    def is_synthetic(self) -> bool:
        """Whether the position is a placeholder, i.e. not derived from an actual source location."""
        return self.start_line < 0

    @model_validator(mode="before")
    def _coerce_from_ansible_position(cls, value: object) -> object:
        """Coerce Ansible's raw `(file, line, column)` position tuple into the model's fields."""
        try:
            file, line, column = cast(
                RawPosition, RawPositionAdapter.validate_python(value)
            )
        except ValidationError:
            return value
        return {"file": Path(file), "start_line": line, "start_column": column}


class BrokenTask(BaseModel, frozen=True):
    """Represents a task/block that could not be extracted."""

    #: The raw datastructure that failed to extract.
    raw: object
    #: The reason for failure.
    reason: str


class BrokenFile(BaseModel, frozen=True):
    """Represents a file that could not be parsed or extracted."""

    #: The relative path to the file in the project.
    path: RelativePath
    #: The reason for failure.
    reason: str


def parse_file(path: ProjectPath) -> object:
    """Parse a YAML file using Ansible's parser."""
    loader = DataLoader()
    return loader.load_from_file(str(path.absolute))
