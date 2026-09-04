"""Paper trading domain: pending entry watches, mark-to-market, stop/target exits.

PAPER / SIMULATED only — never places broker orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

Direction = Literal["LONG", "SHORT"]
PaperStatus = Literal["PENDING", "OPEN", "CLOSED"]
ExitReason = Literal["STOP_LOSS", "TARGET", "MANUAL", "CANCELLED"]


def unrealized_pnl(*, direction: Direction, entry: Decimal, mark: Decimal, quantity: int) -> Decimal:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if direction == "LONG":
        return (mark - entry) * Decimal(quantity)
    return (entry - mark) * Decimal(quantity)


def realized_pnl(*, direction: Direction, entry: Decimal, exit_price: Decimal, quantity: int) -> Decimal:
    return unrealized_pnl(direction=direction, entry=entry, mark=exit_price, quantity=quantity)


def entry_reached(*, direction: Direction, mark: Decimal, entry: Decimal) -> bool:
    """True when live price has reached the planned buy/sell price."""
    if direction == "LONG":
        return mark >= entry
    return mark <= entry


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: ExitReason | None = None
    exit_price: Decimal | None = None


def evaluate_exit(
    *,
    direction: Direction,
    mark: Decimal,
    stop_loss: Decimal,
    target: Decimal,
) -> ExitDecision:
    """If stop and target both hit on the same tick, prefer STOP (conservative)."""
    if direction == "LONG":
        hit_stop = mark <= stop_loss
        hit_target = mark >= target
        if hit_stop:
            return ExitDecision(True, "STOP_LOSS", stop_loss)
        if hit_target:
            return ExitDecision(True, "TARGET", target)
        return ExitDecision(False)
    hit_stop = mark >= stop_loss
    hit_target = mark <= target
    if hit_stop:
        return ExitDecision(True, "STOP_LOSS", stop_loss)
    if hit_target:
        return ExitDecision(True, "TARGET", target)
    return ExitDecision(False)


@dataclass
class PaperTrade:
    symbol: str
    direction: Direction
    entry_price: Decimal
    stop_loss: Decimal
    target: Decimal
    quantity: int
    risk_amount: Decimal | None
    status: PaperStatus
    opened_at: datetime
    id: int | None = None
    scan_run_id: int | None = None
    setup_name: str | None = None
    quality_score: Decimal | None = None
    closed_at: datetime | None = None
    exit_price: Decimal | None = None
    exit_reason: ExitReason | None = None
    last_mark_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    realized_pnl: Decimal | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if self.status not in {"PENDING", "OPEN", "CLOSED"}:
            raise ValueError("status must be PENDING, OPEN, or CLOSED")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        entry = Decimal(str(self.entry_price))
        stop = Decimal(str(self.stop_loss))
        target = Decimal(str(self.target))
        if self.direction == "LONG":
            if not (stop < entry < target):
                raise ValueError("LONG requires stop < entry < target")
        else:
            if not (target < entry < stop):
                raise ValueError("SHORT requires target < entry < stop")
        self.entry_price = entry
        self.stop_loss = stop
        self.target = target

    def activate_at_entry(self, *, now: datetime | None = None) -> None:
        """Fill the practice trade at the planned entry price."""
        if self.status != "PENDING":
            raise ValueError("only PENDING trades can be activated")
        stamp = now or datetime.now(timezone.utc)
        self.status = "OPEN"
        self.opened_at = stamp
        self.last_mark_price = self.entry_price
        self.unrealized_pnl = Decimal("0")
        self.updated_at = stamp

    def apply_mark(self, mark: Decimal, *, now: datetime | None = None) -> ExitDecision:
        if self.status != "OPEN":
            raise ValueError("cannot mark a non-open trade")
        mark = Decimal(str(mark))
        if mark <= 0:
            raise ValueError("mark must be positive")
        decision = evaluate_exit(
            direction=self.direction,
            mark=mark,
            stop_loss=self.stop_loss,
            target=self.target,
        )
        stamp = now or datetime.now(timezone.utc)
        self.last_mark_price = mark
        self.updated_at = stamp
        if decision.should_exit and decision.exit_price is not None and decision.reason is not None:
            self._close(decision.exit_price, decision.reason, stamp)
        else:
            self.unrealized_pnl = unrealized_pnl(
                direction=self.direction,
                entry=self.entry_price,
                mark=mark,
                quantity=self.quantity,
            )
        return decision

    def close_manual(self, price: Decimal, *, now: datetime | None = None) -> None:
        if self.status == "CLOSED":
            raise ValueError("trade is already closed")
        if self.status == "PENDING":
            stamp = now or datetime.now(timezone.utc)
            self.status = "CLOSED"
            self.exit_reason = "CANCELLED"
            self.exit_price = None
            self.closed_at = stamp
            self.updated_at = stamp
            self.realized_pnl = Decimal("0")
            self.unrealized_pnl = Decimal("0")
            return
        self._close(Decimal(str(price)), "MANUAL", now or datetime.now(timezone.utc))

    def _close(self, exit_price: Decimal, reason: ExitReason, when: datetime) -> None:
        self.status = "CLOSED"
        self.exit_price = exit_price
        self.exit_reason = reason
        self.closed_at = when
        self.updated_at = when
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
    "PaperStatus",
    "ExitReason",
    "ExitDecision",
    "PaperTrade",
    "unrealized_pnl",
    "realized_pnl",
    "evaluate_exit",
    "entry_reached",
]
