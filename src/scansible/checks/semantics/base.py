from __future__ import annotations

from pydantic import BaseModel

from scansible.representations.pdg.extractor.context import VisibilityInformation
from scansible.representations.pdg.representation import Graph, NodeLocation


class RuleResult(BaseModel, frozen=True, strict=True, extra="forbid"):
    rule_category: str
    rule_name: str
    rule_subname: str
    rule_header: str
    rule_message: str

    role_name: str
    role_version: str
    location: NodeLocation | None


class Rule:
    def scan(
        self, graph: Graph, visinfo: VisibilityInformation
    ) -> list[RuleResult]: ...
