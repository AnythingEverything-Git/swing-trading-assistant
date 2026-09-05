"""Unit tests for plan-deduction rephrase guardrails."""
from __future__ import annotations

from app.application.narrative.deduction_rephraser import (
    DeductionStep,
    merge_rephrased_steps,
)


def _step(**kwargs) -> DeductionStep:
    base = dict(
        id="entry",
        title="2. Buy/sell at (entry)",
        value="₹100.00",
        summary="Entry is the close of the confirmation candle.",
        details=("Risk per share = ₹5.00.", "Ceiling: ₹99.00."),
    )
    base.update(kwargs)
    return DeductionStep(
        id=base["id"],
        title=base["title"],
        value=base["value"],
        summary=base["summary"],
        details=tuple(base["details"]),
    )


def test_merge_keeps_title_value_and_accepts_grounded_wording():
    source = (_step(),)
    llm = [
        {
            "id": "entry",
            "summary": "We use the confirmation candle close as the entry price.",
            "details": ["Risk for each share stays ₹5.00.", "The ceiling level is ₹99.00."],
        }
    ]
    merged = merge_rephrased_steps(source, llm)
    assert merged is not None
    assert merged[0].title == source[0].title
    assert merged[0].value == source[0].value
    assert "confirmation candle close" in merged[0].summary
    assert "5.00" in merged[0].details[0]


def test_merge_rejects_novel_numbers():
    source = (_step(),)
    llm = [
        {
            "id": "entry",
            "summary": "Entry looks good near ₹112.50.",
            "details": ["Risk per share = ₹5.00."],
        }
    ]
    merged = merge_rephrased_steps(source, llm)
    assert merged is not None
    assert merged[0].summary == source[0].summary
    assert merged[0].details == source[0].details


def test_merge_falls_back_when_step_missing():
    source = (_step(), _step(id="stop", title="3. Safety exit", value="₹95.00"))
    llm = [
        {
            "id": "entry",
            "summary": "We use the confirmation candle close as the entry.",
            "details": ["Risk per share = ₹5.00.", "Ceiling: ₹99.00."],
        }
    ]
    merged = merge_rephrased_steps(source, llm)
    assert merged is not None
    assert len(merged) == 2
    assert merged[1] == source[1]
