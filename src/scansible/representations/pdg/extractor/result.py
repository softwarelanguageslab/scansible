from __future__ import annotations

from typing import overload, TypeVar, Type

import itertools
from collections.abc import Sequence

from attrs import frozen

from ..representation import ControlNode, Variable


_T = TypeVar('_T')


def _join_sequences(seq1: Sequence[_T], seq2: Sequence[_T]) -> Sequence[_T]:
    return list(itertools.chain(seq1, seq2))


def _ensure_sequence(obj: _T | Sequence[_T] | None) -> Sequence[_T]:
    if obj is None:
        return []
    if isinstance(obj, Sequence):
        return obj
    return [obj]


@frozen
class ExtractionResult:
    """The result of an extraction of an element."""

    #: The control nodes added in this extraction.
    added_control_nodes: Sequence[ControlNode]
    #: The variable nodes added in this extraction that are still visible after
    #: the element was left (e.g. included vars, non-persistent facts, but not
    #: task vars).
    added_variable_nodes: Sequence[Variable]
    #: The next control flow predecessors after this extraction.
    next_predecessors: Sequence[ControlNode]

    @classmethod
    def empty(cls, predecessors: Sequence[ControlNode] | None = None) -> ExtractionResult:
        return cls([], [], [] if predecessors is None else predecessors)

    def add_control_nodes(self, nodes: ControlNode | Sequence[ControlNode]) -> ExtractionResult:
        """Add new control nodes to result."""
        return self._extend(added_control_nodes=nodes)

    def add_variable_nodes(self, nodes: Variable | Sequence[Variable]) -> ExtractionResult:
        """Add new variable nodes to result."""
        return self._extend(added_variable_nodes=nodes)

    def add_next_predecessors(self, nodes: ControlNode | Sequence[ControlNode]) -> ExtractionResult:
        """Add new next predecessors to result, keeping the pre-existing ones."""
        return self._extend(next_predecessors=_join_sequences(self.next_predecessors, _ensure_sequence(nodes)))

    def replace_next_predecessors(self, nodes: ControlNode | Sequence[ControlNode]) -> ExtractionResult:
        """Replace next predecessors with new sequence."""
        return self._extend(next_predecessors=nodes)

    def merge(self, other: ExtractionResult) -> ExtractionResult:
        """Merge two results, merging the contents of their fields.

        Next predecessors are also merged."""
        return self._extend(
            added_control_nodes=other.added_control_nodes,
            added_variable_nodes=other.added_variable_nodes,
            next_predecessors=_join_sequences(self.next_predecessors, other.next_predecessors))

    def chain(self, other: ExtractionResult) -> ExtractionResult:
        """Chain two results, discarding `self`'s next predecessors in favour of `other`'s.

        Throws error if other's next predecessors are empty.
        """
        if not other.next_predecessors:
            raise ValueError('Next predecessors would be overwritten by empty list, you probably want to merge instead of chain.')
        return self._extend(
            added_control_nodes=other.added_control_nodes,
            added_variable_nodes=other.added_variable_nodes,
            next_predecessors=other.next_predecessors)

    def _extend(
            self, *,
            added_control_nodes: ControlNode | Sequence[ControlNode] | None = None,
            added_variable_nodes: Variable | Sequence[Variable] | None = None,
            next_predecessors: ControlNode | Sequence[ControlNode] | None = None,
    ) -> ExtractionResult:
        return ExtractionResult(
            _join_sequences(self.added_control_nodes, _ensure_sequence(added_control_nodes)),
            _join_sequences(self.added_variable_nodes, _ensure_sequence(added_variable_nodes)),
            self.next_predecessors if next_predecessors is None else _ensure_sequence(next_predecessors))
