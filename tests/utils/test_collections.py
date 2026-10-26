# pyright: reportUnusedFunction = false

from __future__ import annotations

import pytest

from scansible.utils.collections import (
    FrozenDict,
    ensure_sequence,
    first,
    first_where,
    join_sequences,
)


def describe_first() -> None:
    def should_return_none_for_empty() -> None:
        assert first([]) is None

    def should_return_first_element() -> None:
        assert first([1, 2, 3]) == 1

    def should_work_on_generators() -> None:
        assert first(x for x in range(3)) == 0


def describe_first_where() -> None:
    def should_return_none_without_match() -> None:
        assert first_where([1, 2, 3], lambda x: x > 5) is None

    def should_return_first_match() -> None:
        assert first_where([1, 2, 3], lambda x: x > 1) == 2

    def should_return_none_for_empty() -> None:
        assert first_where([], lambda _: True) is None

    def should_return_first_item_if_it_matches() -> None:
        assert first_where([1, 2, 3], lambda x: x == 1) == 1


def describe_frozen_dict() -> None:
    def should_allow_reads() -> None:
        assert FrozenDict({"a": 1})["a"] == 1

    def should_reject_writes() -> None:
        d = FrozenDict({"a": 1})
        with pytest.raises(RuntimeError):
            d["a"] = 2
        assert d["a"] == 1

    def should_hash_equal_contents_equally() -> None:
        assert hash(FrozenDict({"a": 1, "b": 2})) == hash(FrozenDict({"b": 2, "a": 1}))

    def should_hash_different_contents_differently() -> None:
        assert hash(FrozenDict({"a": 1})) != hash(FrozenDict({"a": 2}))

    def should_be_usable_as_set_member() -> None:
        assert len({FrozenDict({"a": 1}), FrozenDict({"a": 1})}) == 1


def describe_join_sequences() -> None:
    def should_concatenate() -> None:
        assert join_sequences([1, 2], [3, 4]) == (1, 2, 3, 4)

    def should_handle_both_empty() -> None:
        assert join_sequences([], []) == ()

    def should_handle_empty_lhs() -> None:
        assert join_sequences([], [1]) == (1,)

    def should_handle_empty_rhs() -> None:
        assert join_sequences([1], []) == (1,)

    def should_keep_duplicates() -> None:
        assert join_sequences([1, 2], [2, 1]) == (1, 2, 2, 1)


def describe_ensure_sequence() -> None:
    def should_turn_none_into_empty() -> None:
        assert ensure_sequence(None) == []

    def should_return_sequences_unchanged() -> None:
        seq = [1, 2]
        assert ensure_sequence(seq) is seq

    def should_not_wrap_strings() -> None:
        assert ensure_sequence("abc") == "abc"

    def should_wrap_scalars() -> None:
        assert ensure_sequence(5) == [5]
