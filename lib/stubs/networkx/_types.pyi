from __future__ import annotations

from typing import Hashable, TypeVar

NodeT = TypeVar("NodeT", bound=Hashable)
GraphAttrT = TypeVar("GraphAttrT")
EdgeAttrT = TypeVar("EdgeAttrT")
