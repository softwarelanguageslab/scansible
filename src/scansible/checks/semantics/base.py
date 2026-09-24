from __future__ import annotations

from typing import TYPE_CHECKING, override

import abc

from ..base import CheckContext, Finding, RuleBase

if TYPE_CHECKING:
    from scansible.pdg.representation import Graph


class TraversalRule(RuleBase, abc.ABC):
    """Base class for semantics rules that detect issues through bespoke traversal of the PDG."""

    @abc.abstractmethod
    def detect(self, graph: Graph) -> list[Finding]:
        """Traverse the graph and return any findings."""
        raise NotImplementedError

    @override
    def check(self, context: CheckContext) -> list[Finding]:
        return self.detect(context.graph)
