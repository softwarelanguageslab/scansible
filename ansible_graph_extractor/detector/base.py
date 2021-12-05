from pydantic import BaseModel

from ..models.graph import Graph

class RuleResult(BaseModel):
    rule_name: str
    role_name: str
    description: str

class Rule:
    def scan(self, graph: Graph) -> list[RuleResult]:
        ...
