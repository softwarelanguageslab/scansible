"""tqdm typed interface."""
# pylint: skip-file

from typing import Any, Dict, Iterable, Iterator, Optional, Union
from io import StringIO, TextIOWrapper


class tqdm:
    n: int
    total: int
    start_t: float

    def __init__(
            self,
            iterable: Optional[Iterable[Any]] = ...,
            desc: Optional[str] = ...,
            total: Optional[int] = ...,
            leave: bool = ...,
            file: Optional[Union[TextIOWrapper, StringIO]] = ...,
            ncols: Optional[int] = ...,
            mininterval: float = ...,
            maxinterval: float = ...,
            miniters: Optional[int] = ...,
            ascii: Optional[bool] = ...,
            disable: bool = ...,
            unit: str = ...,
            unit_scale: Union[bool, int, float] = ...,
            dynamic_ncols: bool = ...,
            smoothing: float = ...,
            bar_format: Optional[str] = ...,
            initial: int = ...,
            position: Optional[int] = ...,
            postfix: Optional[Any] = ...,
            unit_divisor: int = ...,
            gui: bool = ...,
            **kwargs: Dict[str, Any],
    ) -> None:
        ...

    def set_description(
            self,
            desc: Optional[str] = ...,
            refresh: bool = ...,
    ) -> None:
        ...

    def refresh(self, nolock: bool = ...) -> None:
        ...

    def close(self) -> None:
        ...

    def __iter__(self) -> Iterator[Any]:
        ...

    def update(self, n: int) -> None:
        ...

    @classmethod
    def write(cls, s: str) -> None:
        ...
