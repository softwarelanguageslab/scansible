from __future__ import annotations

from typing import TYPE_CHECKING

from scansible.utils import ensure_sequence, join_sequences

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..representation import ControlNode


class BuildResult:
    """The result of building an element."""

    #: The control nodes added in this build step.
    added_control_nodes: Sequence[ControlNode]
    #: The next control flow predecessors after this build step.
    next_predecessors: Sequence[ControlNode]

    def __init__(
        self,
        added_control_nodes: Sequence[ControlNode] | ControlNode,
        next_predecessors: Sequence[ControlNode] | ControlNode,
    ) -> None:
        self.added_control_nodes = ensure_sequence(added_control_nodes)
        self.next_predecessors = ensure_sequence(next_predecessors)

    @classmethod
    def single(cls, node: ControlNode) -> BuildResult:
        return cls(node, node)

    @classmethod
    def empty(cls, predecessors: Sequence[ControlNode] | None = None) -> BuildResult:
        return cls([], [] if predecessors is None else predecessors)

    def add_control_nodes(
        self, nodes: ControlNode | Sequence[ControlNode]
    ) -> BuildResult:
        """Add new control nodes to result."""
        return self._extend(added_control_nodes=nodes)

    def add_next_predecessors(
        self, nodes: ControlNode | Sequence[ControlNode]
    ) -> BuildResult:
        """Add new next predecessors to result, keeping the pre-existing ones."""
        return self._extend(
            next_predecessors=join_sequences(
                self.next_predecessors, ensure_sequence(nodes)
            )
        )

    def replace_next_predecessors(
        self, nodes: ControlNode | Sequence[ControlNode]
    ) -> BuildResult:
        """Replace next predecessors with new sequence."""
        return self._extend(next_predecessors=nodes)

    def merge(self, other: BuildResult) -> BuildResult:
        """Merge two results, merging the contents of their fields.

        Next predecessors are also merged."""
        return self._extend(
            added_control_nodes=other.added_control_nodes,
            next_predecessors=join_sequences(
                self.next_predecessors, other.next_predecessors
            ),
        )

    def chain(self, other: BuildResult) -> BuildResult:
        """Chain two results, discarding `self`'s next predecessors in favour of `other`'s.

        Throws error if other's next predecessors are empty while the current's next predecessors are not.
        """
        if not other.next_predecessors and self.next_predecessors:
            raise ValueError(
                "Next predecessors would be overwritten by empty list, you probably want to merge instead of chain."
            )
        return self._extend(
            added_control_nodes=other.added_control_nodes,
            next_predecessors=other.next_predecessors,
        )

    def _extend(
        self,
        *,
        added_control_nodes: ControlNode | Sequence[ControlNode] | None = None,
        next_predecessors: ControlNode | Sequence[ControlNode] | None = None,
    ) -> BuildResult:
        return BuildResult(
            join_sequences(
                self.added_control_nodes, ensure_sequence(added_control_nodes)
            ),
            self.next_predecessors
            if next_predecessors is None
            else ensure_sequence(next_predecessors),
        )
