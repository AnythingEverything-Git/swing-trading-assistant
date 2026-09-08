"""Sellable EP5 — Ask TradePilot grounded guardrails."""

import asyncio

from app.api.routes.ai_copilot import AskRequest, _grounded_answer, ask_tradepilot


def test_refuse_invented_levels_without_evidence() -> None:
    out = _grounded_answer("What entry and stop should I use?", {})
    assert out["refused_invention"] is True
    assert "engine" in out["answer"].lower() or "levels" in out["answer"].lower()


def test_repeat_levels_from_evidence_only() -> None:
    out = _grounded_answer(
        "What is my entry and target?",
        {"evidence": {"symbol": "RELIANCE", "entry": "2500", "target": "2600", "stop": "2450"}},
    )
    assert out["refused_invention"] is False
    assert "2500" in out["answer"]
    assert "2600" in out["answer"]
    assert "2450" in out["answer"]


def test_explain_reason_code() -> None:
    out = _grounded_answer(
        "Why was this blocked?",
        {"symbol": "XYZ", "reason": "SURVEILLANCE_BLOCKED"},
    )
    assert "SURVEILLANCE_BLOCKED" in out["answer"]


def test_ask_endpoint_shape() -> None:
    body = asyncio.run(
        ask_tradepilot(AskRequest(question="Explain eligibility", context={"reason": "RANKED_ARMED"}))
    )
    assert "answer" in body
    assert body.get("claim")
