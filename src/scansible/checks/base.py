from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import abc
from dataclasses import dataclass

from pydantic import BaseModel

from scansible.pdg import Graph
from scansible.pdg.representation import NodeLocation

if TYPE_CHECKING:
    from .security.db import GraphDatabase


class Finding(BaseModel, frozen=True, strict=True, extra="forbid"):
    #: Stable identifier of the rule that produced this finding, e.g. "SEC003", "SEM005".
    code: str
    #: One-line, finding-specific diagnostic message.
    summary: str
    #: Optional, longer rationale, only populated when it adds something beyond the summary.
    explanation: str = ""
    #: Primary location of the finding.
    location: NodeLocation
    #: Optional secondary, related location (e.g. "previous definition here").
    hint_location: NodeLocation | None = None
    #: Description of what the hint location refers to. Only meaningful together with `hint_location`.
    hint_text: str = ""


@dataclass(frozen=True)
class CheckContext:
    #: The PDG being checked.
    graph: Graph
    #: The graph database used by `GraphDBRule`s, populated lazily by the runner
    #: only when at least one enabled rule needs it.
    db: GraphDatabase | None = None


class RuleBase(abc.ABC):
    #: Stable identifier of this rule, e.g. "SEC003", "SEM005".
    code: ClassVar[str]

    @abc.abstractmethod
    def check(self, context: CheckContext) -> list[Finding]:
        """Run this rule and return its findings."""
        raise NotImplementedError
