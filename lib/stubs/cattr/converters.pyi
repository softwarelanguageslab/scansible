from __future__ import annotations

from typing import Any, Callable, Dict, Type, TypeVar

from enum import Enum

NoneType: Any
T = TypeVar("T")
V = TypeVar("V")

class UnstructureStrategy(Enum):
    AS_DICT: str
    AS_TUPLE: str

class Converter:
    def __init__(
        self,
        dict_factory: Callable[[], Dict[Any, Any]] = ...,
        unstruct_strat: UnstructureStrategy = ...,
    ) -> None: ...
    def unstructure(self, obj: Any) -> Any: ...
    @property
    def unstruct_strat(self) -> UnstructureStrategy: ...
    def register_unstructure_hook(
        self, cls: Type[T], func: Callable[[T], Any]
    ) -> None: ...
    def register_structure_hook(
        self, cl: Type[T], func: Callable[[Any, Type[T]], T]
    ) -> None: ...
    def structure(self, obj: Any, cl: Type[T]) -> T: ...
