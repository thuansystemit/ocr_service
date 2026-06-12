"""Confidence scorer unit tests (T-051)."""

from __future__ import annotations

import pytest

from app.domain.confidence import (
    completeness_score,
    missing_required,
    route,
    score,
)


def test_completeness_all_present() -> None:
    assert completeness_score({"a": "1", "b": "2"}, ["a", "b"]) == 1.0


def test_completeness_partial_and_empty_values() -> None:
    assert completeness_score({"a": "1", "b": "", "c": None}, ["a", "b", "c"]) == pytest.approx(
        1 / 3
    )


def test_completeness_no_required_is_full() -> None:
    assert completeness_score({}, []) == 1.0


def test_score_is_minimum_times_multiplier() -> None:
    b = score(llm_self=0.9, completeness=0.5, semantic=0.8, guardrail_multiplier=1.0)
    assert b.guardrail_adjusted == 0.5  # min wins
    b2 = score(llm_self=0.9, completeness=0.9, semantic=0.9, guardrail_multiplier=0.8)
    assert b2.guardrail_adjusted == pytest.approx(0.72)


def test_missing_required() -> None:
    assert missing_required({"a": "x", "b": ""}, ["a", "b", "c"]) == ["b", "c"]


@pytest.mark.parametrize(
    ("conf", "expected"),
    [(0.85, "HIGH"), (0.84, "MEDIUM"), (0.60, "MEDIUM"), (0.59, "LOW"), (0.0, "LOW")],
)
def test_route_thresholds_inclusive_upper(conf: float, expected: str) -> None:
    assert route(conf, high=0.85, medium=0.60) == expected
