from typing import Any, Optional, Iterator

from .symbolic import SymbolicReference
from ..util import Iterable, LazyMixin
from ..objects.base import Object
Repo = Any # from ..repo import Repo

class Reference(SymbolicReference, LazyMixin, Iterable):
    def __init__(self, repo: Repo, path: str, check_path: bool = ...) -> None: ...
    def set_object(self, object: Object, logmsg: Optional[str] = ...) -> Reference: ...  # type: ignore[override]
    @property
    def name(self) -> str: ...
    @classmethod
    def iter_items(cls, repo: Repo, common_path: Optional[str] = ...) -> Iterator[Reference]: ...
    @property
    def remote_name(self) -> str: ...
    @property
    def remote_head(self) -> str: ...
