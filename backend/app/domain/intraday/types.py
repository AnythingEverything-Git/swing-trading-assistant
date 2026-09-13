"""Shared types for the intraday ORB domain engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Sequence

Direction = Literal["LONG", "SHORT"]
SideOutcome = Literal[
    "TRADED",
    "DOJI",
    "INSUFFICIENT_RVOL",
    "INSUFFICIENT_HISTORY",
    "INSUFFICIENT_LIQUIDITY",
    "SPREAD_TOO_WIDE",
    "SURVEILLANCE_BLOCKED",
    "PRICE_BAND_RISK",
    "CORPORATE_ACTION_BLOCK",
    "SHORT_NOT_PERMITTED",
    "ETF_FILTER",
    "SPECIAL_SESSION_SKIP",
    "BREAKOUT_NOT_TRIGGERED",
    "ENTRY_CUTOFF",
    "RISK_INVALID",
    "PORTFOLIO_RISK_LIMIT",
    "DAILY_LOSS_LOCK",
    "CONSECUTIVE_LOSS_LOCK",
    "DATA_STALE",
    "ORDER_REJECTED",
    "NO_SETUP",
    "NOT_IN_TOP_N",
    "RANKED_ARMED",
]


@dataclass(frozen=True)
class OpeningRange:
    symbol: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    bar_open: datetime

    @property
    def expansion_pct(self) -> Decimal:
        if self.open <= 0:
            return Decimal("0")
        return (self.high - self.low) / self.open


@dataclass(frozen=True)
class ScreenCandidate:
    symbol: str
    instrument_id: str
    direction: Direction
    opening_range: OpeningRange
    rvol5: Decimal
    adv_value: Decimal
    prior_atr14: Decimal
    short_allowed: bool = True
    spread: Decimal = Decimal("0")
    tick_size: Decimal = Decimal("0.05")
    asset_class: Literal["STOCK", "ETF"] = "STOCK"


@dataclass(frozen=True)
class RankedCandidate:
    candidate: ScreenCandidate
    rank: int


@dataclass(frozen=True)
class SymbolResult:
    symbol: str
    reason: SideOutcome
    rank: int | None = None
    rvol5: Decimal | None = None
    direction: Direction | None = None
    detail: str | None = None
    asset_class: Literal["STOCK", "ETF"] | None = None


@dataclass(frozen=True)
class FillPlan:
    symbol: str
    direction: Direction
    rank: int
    entry: Decimal
    stop: Decimal
    quantity: int
    stop_distance: Decimal
    effective_risk_per_share: Decimal
    trigger_bar_open: datetime
    risk_amount: Decimal


@dataclass(frozen=True)
class ClosedTrade:
    fill: FillPlan
    exit_price: Decimal
    exit_reason: Literal["STOP", "EOD_EXIT"]
    exit_time: datetime
    pnl: Decimal
    mfe: Decimal = Decimal("0")
    mae: Decimal = Decimal("0")

    @property
    def giveback(self) -> Decimal | None:
        """Fraction of MFE given back on winners: (MFE − exit PnL) / MFE."""
        if self.mfe <= 0 or self.pnl <= 0:
            return None
        return (self.mfe - self.pnl) / self.mfe


@dataclass
class PortfolioState:
    equity: Decimal
    open_fills: list[FillPlan] = field(default_factory=list)
    closed: list[ClosedTrade] = field(default_factory=list)
    consecutive_losses: int = 0
    realized_pnl: Decimal = Decimal("0")
    traded_symbols: set[str] = field(default_factory=set)
    max_risk_per_trade_inr: Decimal | None = None
    max_open_risk_inr: Decimal | None = None
    daily_loss_lock_inr: Decimal | None = None

    @property
    def daily_loss_locked(self) -> bool:
        return False  # evaluated via helpers with config


@dataclass(frozen=True)
class RiskBudgetOverrides:
    """Account-level absolute ₹ caps layered on CONFIG_V1 percentages."""

    max_risk_per_trade_inr: Decimal | None = None
    max_open_risk_inr: Decimal | None = None
    daily_loss_lock_inr: Decimal | None = None

    def nonempty(self) -> bool:
        return any(
            v is not None and v > 0
            for v in (self.max_risk_per_trade_inr, self.max_open_risk_inr, self.daily_loss_lock_inr)
        )


@dataclass(frozen=True)
class SessionReport:
    session_date: date
    strategy_id: str
    config_hash: str
    symbol_results: Sequence[SymbolResult]
    fills: Sequence[FillPlan]
    closed_trades: Sequence[ClosedTrade]
    coverage_eligible: int
    coverage_total: int
    ranked_stocks: Sequence[RankedCandidate] = ()
    ranked_etfs: Sequence[RankedCandidate] = ()


__all__ = [
    "Direction",
    "SideOutcome",
    "OpeningRange",
    "ScreenCandidate",
    "RankedCandidate",
    "SymbolResult",
    "FillPlan",
    "ClosedTrade",
    "PortfolioState",
    "RiskBudgetOverrides",
    "SessionReport",
]
