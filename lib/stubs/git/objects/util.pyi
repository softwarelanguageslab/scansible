from datetime import tzinfo
from git.util import Actor as Actor
from typing import Any, Optional, TypeVar, Generic, Callable, Iterator, List

_V = TypeVar('_V')

class Traversable(Generic[_V]):
    def list_traverse(self, predicate: Callable[[_V, int], bool] = ..., prune: Callable[[_V, int], bool] = ..., depth: int = ..., branch_first: bool = ..., visit_once: bool = ..., ignore_self: int = ..., as_edge: bool = ...) -> List[_V]: ...
    def traverse(self, predicate: Callable[[_V, int], bool] = ..., prune: Callable[[_V, int], bool] = ..., depth: int = ..., branch_first: bool = ..., visit_once: bool = ..., ignore_self: int = ..., as_edge: bool = ...) -> Iterator[_V]: ...

class Serializable: ...
