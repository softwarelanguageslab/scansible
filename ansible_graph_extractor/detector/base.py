from pydantic import BaseModel

from ..models.graph import Graph

class RuleResult(BaseModel):
    role_name: str
    description: str

class Rule:
    def scan(self, graph: Graph) -> list[RuleResult]:
        ...
