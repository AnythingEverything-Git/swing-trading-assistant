"""Intraday ORB practice trades — stop-only + 15:10 flatten (no profit goal).

PAPER / SIMULATED only — never places broker orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from app.domain.paper import unrealized_pnl, realized_pnl

IST = ZoneInfo("Asia/Kolkata")

Direction = Literal["LONG", "SHORT"]
PracticeStatus = Literal["OPEN", "CLOSED"]
PracticeExitReason = Literal["STOP", "EOD_EXIT", "MANUAL"]


@dataclass(frozen=True)
class PracticeExitDecision:
    should_exit: bool
    reason: PracticeExitReason | None = None
    exit_price: Decimal | None = None


def evaluate_orb_exit(
    *,
    direction: Direction,
    mark: Decimal,
    stop_loss: Decimal,
    now_ist: datetime,
    forced_exit: time = time(15, 10),
) -> PracticeExitDecision:
    """Stop hit wins over clock; after forced_exit → flatten at mark."""
    if direction == "LONG":
        if mark <= stop_loss:
            return PracticeExitDecision(True, "STOP", stop_loss)
    else:
        if mark >= stop_loss:
            return PracticeExitDecision(True, "STOP", stop_loss)

    local = now_ist.astimezone(IST) if now_ist.tzinfo else now_ist.replace(tzinfo=IST)
    if local.time() >= forced_exit:
        return PracticeExitDecision(True, "EOD_EXIT", mark)
    return PracticeExitDecision(False)


@dataclass
class IntradayPracticeTrade:
    symbol: str
    direction: Direction
    entry_price: Decimal
    stop_loss: Decimal
    quantity: int
    session_date: date
    session_id: str
    status: PracticeStatus = "OPEN"
    id: int | None = None
    risk_amount: Decimal | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    exit_price: Decimal | None = None
    exit_reason: PracticeExitReason | None = None
    last_mark_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    realized_pnl: Decimal | None = None
    strategy_id: str = "NSE_STOCKS_ETF_ORB_RVOL_5M_V1"
    config_hash: str = "CONFIG_V1"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        entry = Decimal(str(self.entry_price))
        stop = Decimal(str(self.stop_loss))
        if self.direction == "LONG" and not (stop < entry):
            raise ValueError("LONG requires stop < entry")
        if self.direction == "SHORT" and not (stop > entry):
            raise ValueError("SHORT requires stop > entry")
        self.entry_price = entry
        self.stop_loss = stop
        if self.last_mark_price is None and self.status == "OPEN":
            self.last_mark_price = entry
            self.unrealized_pnl = Decimal("0")

    def apply_mark(self, mark: Decimal, *, now: datetime) -> PracticeExitDecision:
        if self.status != "OPEN":
            raise ValueError("cannot mark a non-open trade")
        mark = Decimal(str(mark))
        if mark <= 0:
            raise ValueError("mark must be positive")
        decision = evaluate_orb_exit(
            direction=self.direction,
            mark=mark,
            stop_loss=self.stop_loss,
            now_ist=now,
        )
        self.last_mark_price = mark
        if decision.should_exit and decision.exit_price is not None and decision.reason is not None:
            self._close(decision.exit_price, decision.reason, now)
        else:
            self.unrealized_pnl = unrealized_pnl(
                direction=self.direction,
                entry=self.entry_price,
                mark=mark,
                quantity=self.quantity,
            )
        return decision

    def close_manual(self, price: Decimal, *, now: datetime) -> None:
        if self.status != "OPEN":
            raise ValueError("only OPEN trades can be closed manually")
        self._close(Decimal(str(price)), "MANUAL", now)

    def _close(self, exit_price: Decimal, reason: PracticeExitReason, when: datetime) -> None:
        self.status = "CLOSED"
        self.exit_price = exit_price
        self.exit_reason = reason
        self.closed_at = when
        self.last_mark_price = exit_price
        self.realized_pnl = realized_pnl(
            direction=self.direction,
            entry=self.entry_price,
            exit_price=exit_price,
            quantity=self.quantity,
        )
        self.unrealized_pnl = Decimal("0")


__all__ = [
    "Direction",
    "PracticeStatus",
    "PracticeExitReason",
    "PracticeExitDecision",
    "IntradayPracticeTrade",
    "evaluate_orb_exit",
]
