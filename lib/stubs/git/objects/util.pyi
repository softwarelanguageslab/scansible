from __future__ import annotations

from typing import Any, Callable, Generic, Iterator, List, Optional, TypeVar

from datetime import tzinfo

from git.util import Actor as Actor

_V = TypeVar("_V")

class Traversable(Generic[_V]):
    def list_traverse(
        self,
        predicate: Callable[[_V, int], bool] = ...,
        prune: Callable[[_V, int], bool] = ...,
        depth: int = ...,
        branch_first: bool = ...,
        visit_once: bool = ...,
        ignore_self: int = ...,
        as_edge: bool = ...,
    ) -> List[_V]: ...
    def traverse(
        self,
        predicate: Callable[[_V, int], bool] = ...,
        prune: Callable[[_V, int], bool] = ...,
        depth: int = ...,
        branch_first: bool = ...,
        visit_once: bool = ...,
        ignore_self: int = ...,
        as_edge: bool = ...,
    ) -> Iterator[_V]: ...

class Serializable: ...
