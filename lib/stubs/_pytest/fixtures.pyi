from typing import (Any, Callable, List, Mapping, NoReturn, Optional, Tuple,
                    Type)
from typing_extensions import Literal
from types import FunctionType, ModuleType

SCOPE = Literal['function', 'class', 'module', 'session']


class FuncFixtureInfo:
    argnames: Tuple[str]
    initialnames: Tuple[str]
    names_closure: List[str]
    name2fixturedefs: Mapping[str, List[FixtureDef]]


class FixtureDef:
    ...


class FixtureRequest:
    @property
    def module(self) -> ModuleType:
        ...

    @property
    def function(self) -> FunctionType:
        ...

    @property
    def cls(self) -> Optional[type]:
        ...

    def addfinalizer(self, finalizer: Callable[[], None]) -> None:
        ...


class SubRequest(FixtureRequest):
    fixturename: str
    param: Any
    param_index: int
    scope: SCOPE
