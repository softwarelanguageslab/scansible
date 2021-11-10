from .head import Head
Repo = Any #from ..repo import Repo
from typing import Any, Optional, Iterator, NoReturn

class RemoteReference(Head):
    @classmethod
    def iter_items(cls, repo: Repo, common_path: Optional[str] = ..., remote: Optional[str] = ...) -> Iterator[RemoteReference]: ...
    @classmethod
    def delete(cls, repo: Repo, *refs: RemoteReference, **kwargs: Any) -> None: ...  # type: ignore[override]
    @classmethod
    def create(cls, *args: Any, **kwargs: Any) -> NoReturn: ...
