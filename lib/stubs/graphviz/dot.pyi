from __future__ import annotations

from typing import (
    ContextManager,
    Iterable,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    overload,
)

from types import TracebackType

from . import files
from .backend import _EngineValue, _FormatValue  # pyright: ignore

Attrs = Mapping[str, str]

_Self = TypeVar("_Self", bound=Dot)
_GraphType = TypeVar("_GraphType", bound=Dot)

class Dot(files.File):
    name: str = ...
    comment: str = ...
    body: Iterable[str] = ...
    graph_attr: Attrs = ...
    edge_attr: Attrs = ...
    node_attr: Attrs = ...
    strict: bool = ...
    def __init__(
        self,
        name: Optional[str] = ...,
        comment: Optional[str] = ...,
        filename: Optional[str] = ...,
        directory: Optional[str] = ...,
        format: Optional[_FormatValue] = ...,
        engine: Optional[_EngineValue] = ...,
        encoding: str = ...,
        graph_attr: Optional[Attrs] = ...,
        node_attr: Optional[Attrs] = ...,
        edge_attr: Optional[Attrs] = ...,
        body: Optional[Iterable[str]] = ...,
        strict: bool = ...,
    ) -> None: ...
    def clear(self, keep_attrs: bool = ...) -> None: ...
    def __iter__(self, subgraph: bool = ...) -> Iterable[str]: ...
    source: str = ...
    def node(self, name: str, label: Optional[str] = ..., **attrs: str) -> None: ...
    def edge(
        self,
        tail_name: str,
        head_name: str,
        label: Optional[str] = ...,
        _attributes: Optional[Attrs] = ...,
        **attrs: str,
    ) -> None: ...
    def edges(self, tail_head_iter: Iterable[Tuple[str, str]]) -> None: ...
    def attr(
        self, kw: Optional[str] = ..., _attributes: Optional[Attrs] = ..., **attrs: str
    ) -> None: ...
    @overload
    def subgraph(self: _Self, graph: _Self) -> None: ...
    @overload
    def subgraph(
        self: _Self,
        name: Optional[str] = ...,
        comment: Optional[str] = ...,
        graph_attr: Optional[Attrs] = ...,
        node_attr: Optional[Attrs] = ...,
        edge_attr: Optional[Attrs] = ...,
        body: Optional[Iterable[str]] = ...,
    ) -> SubgraphContext[_Self]: ...

class SubgraphContext(ContextManager[_GraphType]):
    parent: _GraphType = ...
    graph: _GraphType = ...
    def __init__(self, parent: _GraphType, kwargs: Attrs) -> None: ...
    def __enter__(self) -> _GraphType: ...
    def __exit__(
        self,
        type_: Optional[Type[BaseException]],
        value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None: ...

class Graph(Dot):
    @property
    def directed(self) -> Literal[False]: ...

class Digraph(Dot):
    @property
    def directed(self) -> Literal[True]: ...
