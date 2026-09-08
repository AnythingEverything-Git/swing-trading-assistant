"""Scoped Ask TradePilot copilot (sellable EP5) — grounded refusals for invented levels."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

_PRICE_ASK = re.compile(
    r"\b(entry|stop|sl|target|or high|or low|opening range|give me (a |the )?price)\b",
    re.I,
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)


def _grounded_answer(question: str, context: dict[str, Any]) -> dict[str, Any]:
    q = question.strip()
    evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
    symbol = context.get("symbol") or evidence.get("symbol")
    levels = {
        "entry": evidence.get("entry") or evidence.get("entry_price"),
        "stop": evidence.get("stop") or evidence.get("stop_loss"),
        "target": evidence.get("target"),
        "or_high": evidence.get("or_high"),
        "or_low": evidence.get("or_low"),
    }

    if _PRICE_ASK.search(q):
        known = {k: v for k, v in levels.items() if v is not None}
        if not known:
            return {
                "answer": (
                    "I can only repeat Entry / Stop / Target / OR levels that the engine already computed. "
                    "No levels are in context yet — run Find setups or Morning board first."
                ),
                "refused_invention": True,
                "citations": [],
            }
        lines = [f"{k}: {v}" for k, v in known.items()]
        return {
            "answer": "From the current plan evidence only:\n" + "\n".join(lines),
            "refused_invention": False,
            "citations": list(known.keys()),
        }

    if re.search(r"\b(why|explain|blocked|eligible|armed)\b", q, re.I):
        reason = context.get("reason") or evidence.get("reason") or context.get("detail")
        if reason:
            return {
                "answer": f"{symbol or 'This name'}: outcome/reason is **{reason}**. "
                "Numbers come from the strategy engine; I only explain them.",
                "refused_invention": False,
                "citations": ["reason"],
            }
        return {
            "answer": "Ask while a setup or board row is selected so I can cite its reason code.",
            "refused_invention": False,
            "citations": [],
        }

    if re.search(r"\brisk|quantity|size|capital\b", q, re.I):
        qty = evidence.get("quantity") or context.get("quantity")
        risk = evidence.get("risk_amount") or context.get("risk_amount")
        equity = context.get("account_equity")
        bits = []
        if equity:
            bits.append(f"Your capital in context: {equity}")
        if qty is not None:
            bits.append(f"Sized quantity: {qty}")
        if risk is not None:
            bits.append(f"Risk amount: {risk}")
        if bits:
            return {
                "answer": "Risk coach (from context only):\n" + "\n".join(bits),
                "refused_invention": False,
                "citations": ["account_equity", "quantity", "risk_amount"],
            }
        return {
            "answer": "Set Your capital and open a sized setup so I can explain quantity from equity × risk %.",
            "refused_invention": False,
            "citations": [],
        }

    return {
        "answer": (
            "Ask about why a setup is eligible/blocked, risk sizing, or to repeat engine levels. "
            "I will not invent prices or change CONFIG_V1."
        ),
        "refused_invention": False,
        "citations": [],
        "hint": "Scoped to current symbol/scan/session context only.",
    }


@router.post("/ask")
async def ask_tradepilot(payload: AskRequest) -> dict:
    result = _grounded_answer(payload.question, payload.context or {})
    result["claim"] = "Grounded AI — never invents Entry/SL/Target/OR"
    return result


__all__ = ["router", "_grounded_answer"]
