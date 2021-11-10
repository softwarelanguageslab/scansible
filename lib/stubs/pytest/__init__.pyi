"""pytest typed interface."""
# pylint: skip-file

from typing import (Any, AnyStr, ContextManager, Generic, List, NoReturn,
                    Pattern, Type, TypeVar, Union, Literal)

from . import mark
from .mark import Mark

_FT = TypeVar('_FT')


class FixtureFunctionMarker:

    def __call__(self, f: _FT) -> _FT:
        ...


def fixture(
        scope: Literal['module', 'function', 'package', 'class'] = ...,
        autouse: bool = ...
) -> FixtureFunctionMarker:
    ...

_ET = TypeVar('_ET', bound=Exception)

def raises(
        exc_type: Type[_ET],
        match: Union[str, Pattern[AnyStr]] = ...
) -> ContextManager[Any]:
    ...


def warns(
        exc_type: Type[Warning],
        match: Union[str, Pattern[AnyStr]] = ...
) -> ContextManager[None]:
    ...

def param(*param: Any, marks: Union[List[Mark], Mark] = ..., id: str = ...) -> Any:
    ...

def fail(msg: str) -> NoReturn: ...
