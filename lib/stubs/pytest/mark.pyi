"""pytest typed interface."""
# pylint: skip-file

from typing import Any, Callable, Iterable, Optional, Type, TypeVar, Union


FT = TypeVar('FT')

class Mark:
    """Dummy class."""
    def __call__(self, f: FT) -> FT: ...

def filterwarnings(cat: str) -> Callable[[FT], FT]:
    ...

def parametrize(
        attrs: str,
        data: Iterable[Any],
        ids: Optional[Union[Callable[[Any], str], Iterable[str]]] = ...,
        indirect: Union[bool, Iterable[str]] = ...
) -> Callable[[FT], FT]:
    ...

def trylast(f: FT) -> FT:
    ...

def usefixtures(*args: str) -> Callable[[FT], FT]:
    ...

def xfail(raises: Type[Exception] = ..., condition: bool = ..., reason: str = ...) -> Callable[[FT], FT]: ...
def skip(reason: str) -> Any: ...

def __getattr__(name: str) -> Mark: ...