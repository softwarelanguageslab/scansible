from pydantic import BaseModel

from ..models.graph import Graph
from ..extractor.context import VisibilityInformation

class RuleResult(BaseModel):
    rule_category: str
    rule_name: str
    rule_subname: str
    rule_header: str
    rule_message: str

    role_name: str
    role_version: str
    location: str

class Rule:
    def scan(self, graph: Graph, visibility_information: VisibilityInformation) -> list[RuleResult]:
        ...
