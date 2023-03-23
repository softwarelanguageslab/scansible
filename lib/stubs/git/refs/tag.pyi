from __future__ import annotations

from typing import Any, Optional

Repo = Any  # from ..repo import Repo
from ..objects.base import Object
from ..objects.commit import Commit
from ..objects.tag import TagObject
from .reference import Reference

class TagReference(Reference):
    @property
    def commit(self) -> Commit: ...
    @commit.setter
    def commit(self, commit: Commit) -> None: ...
    @property
    def tag(self) -> Optional[TagObject]: ...
    @property  # type: ignore[misc]
    def object(self) -> Object: ...
    @classmethod
    def create(cls, repo: Repo, path: str, ref: str = ..., message: Optional[str] = ..., force: bool = ..., **kwargs: Any) -> TagReference: ...  # type: ignore[override]
    @classmethod
    def delete(cls, repo: Repo, *tags: TagReference) -> None: ...  # type: ignore[override]

Tag = TagReference
