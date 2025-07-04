from __future__ import annotations

from typing import Optional, TypeVar

from .backend import (
    _EngineValue,  # pyright: ignore
    _FormatterValue,  # pyright: ignore
    _FormatValue,  # pyright: ignore
    _RendererValue,  # pyright: ignore
)

_Self = TypeVar("_Self", bound=Base)

class Base:
    @property
    def format(self) -> _FormatValue: ...
    @format.setter
    def format(self, format: _FormatValue) -> None: ...
    @property
    def engine(self) -> _EngineValue: ...
    @engine.setter
    def engine(self, engine: _EngineValue) -> None: ...
    @property
    def encoding(self) -> str: ...
    @encoding.setter
    def encoding(self, encoding: str) -> None: ...
    def copy(self: _Self) -> _Self: ...

class File(Base):
    directory: str = ...
    filename: str = ...
    format: _FormatValue = ...
    engine: _EngineValue = ...
    encoding: str = ...
    def __init__(
        self,
        filename: Optional[str] = ...,
        directory: Optional[str] = ...,
        format: Optional[_FormatValue] = ...,
        engine: Optional[_EngineValue] = ...,
        encoding: str = ...,
    ) -> None: ...
    def pipe(
        self,
        format: Optional[_FormatValue] = ...,
        renderer: Optional[_RendererValue] = ...,
        formatter: Optional[_FormatterValue] = ...,
        quiet: bool = ...,
    ) -> bytes: ...
    @property
    def filepath(self) -> str: ...
    def save(
        self, filename: Optional[str] = ..., directory: Optional[str] = ...
    ) -> str: ...
    def render(
        self,
        filename: Optional[str] = ...,
        directory: Optional[str] = ...,
        view: bool = ...,
        cleanup: bool = ...,
        format: Optional[_FormatValue] = ...,
        renderer: Optional[_RendererValue] = ...,
        formatter: Optional[_FormatterValue] = ...,
        quiet: bool = ...,
        quiet_view: bool = ...,
    ) -> str: ...
    def view(
        self,
        filename: Optional[str] = ...,
        directory: Optional[str] = ...,
        cleanup: bool = ...,
        quiet: bool = ...,
        quiet_view: bool = ...,
    ) -> str: ...

class Source(File):
    @classmethod
    def from_file(
        cls,
        filename: str,
        directory: Optional[str] = ...,
        format: Optional[_FormatValue] = ...,
        engine: Optional[_EngineValue] = ...,
        encoding: str = ...,
    ) -> Source: ...
    source: str = ...
    def __init__(
        self,
        source: str,
        filename: Optional[str] = ...,
        directory: Optional[str] = ...,
        format: Optional[_FormatValue] = ...,
        engine: Optional[_EngineValue] = ...,
        encoding: str = ...,
    ) -> None: ...
