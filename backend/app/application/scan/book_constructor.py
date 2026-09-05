"""Rules-based personal book constructor. LLM only explains after the solver."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.application.backtesting.position_sizing import calculate_position_size
from app.application.narrative.grounded_narrator import GroundedNarrator, GroundedTextResult
from app.application.scan.scan_presentation import PresentedOpportunity


@dataclass(frozen=True)
class BookPick:
    symbol: str
    direction: str
    rank: int
    quality_score: Decimal
    quantity: int
    risk_amount: Decimal
    entry: Decimal
    stop: Decimal
    target: Decimal
    risk_reward_ratio: Decimal


@dataclass(frozen=True)
class BookRejection:
    symbol: str
    reason: str


@dataclass(frozen=True)
class PersonalBook:
    picks: tuple[BookPick, ...]
    rejected: tuple[BookRejection, ...]
    rationale_rules: tuple[str, ...]
    explanation: str | None
    explanation_provider: str


def build_personal_book(
    opportunities: list[PresentedOpportunity] | tuple[PresentedOpportunity, ...],
    *,
    account_equity: Decimal,
    risk_percent: Decimal,
    max_positions: int = 3,
    open_symbols: set[str] | None = None,
) -> PersonalBook:
    """Deterministic solver: take top ranked names that size > 0 and are not already open."""
    open_syms = {s.upper() for s in (open_symbols or set())}
    max_n = max(1, int(max_positions))
    picks: list[BookPick] = []
    rejected: list[BookRejection] = []
    rationale: list[str] = [
        f"Max concurrent positions: {max_n}",
        f"Risk per idea: {risk_percent}% of equity {account_equity}",
        "Skip symbols already OPEN/PENDING in practice book",
        "Skip names that size to 0 shares under risk rules",
        "Order follows scan rank (rules quality score) — LLM does not reorder",
    ]

    seen: set[str] = set()
    for item in opportunities:
        symbol = item.opportunity.symbol.upper()
        if len(picks) >= max_n:
            rejected.append(BookRejection(symbol=symbol, reason="max_positions_reached"))
            continue
        if symbol in seen:
            rejected.append(BookRejection(symbol=symbol, reason="duplicate_symbol"))
            continue
        if symbol in open_syms:
            rejected.append(BookRejection(symbol=symbol, reason="already_open_in_paper"))
            continue
        candidate = item.opportunity.candidate
        sizing = calculate_position_size(account_equity, risk_percent, candidate)
        if sizing.quantity <= 0:
            rejected.append(BookRejection(symbol=symbol, reason="zero_quantity_under_risk"))
            continue
        seen.add(symbol)
        picks.append(
            BookPick(
                symbol=symbol,
                direction=candidate.direction,
                rank=item.rank,
                quality_score=item.quality.score,
                quantity=sizing.quantity,
                risk_amount=sizing.actual_risk_amount,
                entry=candidate.entry_price,
                stop=candidate.stop_loss,
                target=candidate.target,
                risk_reward_ratio=candidate.risk_reward_ratio,
            )
        )

    return PersonalBook(
        picks=tuple(picks),
        rejected=tuple(rejected),
        rationale_rules=tuple(rationale),
        explanation=None,
        explanation_provider="template",
    )


async def explain_personal_book(
    narrator: GroundedNarrator | None,
    book: PersonalBook,
) -> PersonalBook:
    if not book.picks:
        text = "No picks under current capital, risk %, and open-book constraints."
        return PersonalBook(
            picks=book.picks,
            rejected=book.rejected,
            rationale_rules=book.rationale_rules,
            explanation=text,
            explanation_provider="template",
        )

    pick_facts = [
        {
            "symbol": p.symbol,
            "direction": p.direction,
            "rank": p.rank,
            "quality_score": str(p.quality_score),
            "quantity": p.quantity,
            "risk_amount": str(p.risk_amount),
            "entry": str(p.entry),
            "stop": str(p.stop),
            "target": str(p.target),
            "risk_reward_ratio": str(p.risk_reward_ratio),
        }
        for p in book.picks
    ]
    fallback = (
        "Rules selected "
        + ", ".join(f"{p.symbol} (rank {p.rank}, score {p.quality_score})" for p in book.picks)
        + ". Ranking and sizing are rules-based; this text only explains the book."
    )
    facts: dict[str, Any] = {
        "picks": pick_facts,
        "rationale_rules": list(book.rationale_rules),
        "rejected_count": len(book.rejected),
    }
    if narrator is None or not narrator.enabled:
        return PersonalBook(
            picks=book.picks,
            rejected=book.rejected,
            rationale_rules=book.rationale_rules,
            explanation=fallback,
            explanation_provider="template",
        )
    result: GroundedTextResult = await narrator.rephrase_text(
        kind="personal_book",
        source_text=fallback,
        facts=facts,
        instruction=(
            "Explain in 2-3 sentences why these rules-selected picks form a small book. "
            "Do not reorder picks. Do not invent prices. Mention rank/score only from facts."
        ),
    )
    return PersonalBook(
        picks=book.picks,
        rejected=book.rejected,
        rationale_rules=book.rationale_rules,
        explanation=result.text or fallback,
        explanation_provider=result.provider,
    )


__all__ = [
    "BookPick",
    "BookRejection",
    "PersonalBook",
    "build_personal_book",
    "explain_personal_book",
]
