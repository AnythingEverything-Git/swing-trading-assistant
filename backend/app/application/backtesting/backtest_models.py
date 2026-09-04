from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum


def _as_decimal(value: Decimal | int | float | str, field_name: str) -> Decimal:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal value") from exc
    return decimal_value


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TARGET = "TARGET"
    GAP_THROUGH_STOP = "GAP_THROUGH_STOP"
    GAP_THROUGH_TARGET = "GAP_THROUGH_TARGET"
    END_OF_DATA = "END_OF_DATA"
    OPEN = "OPEN"


@dataclass(frozen=True)
class BacktestTrade:
    symbol: str
    timeframe: str
    setup_time: datetime
    entry_time: datetime
    entry_price: Decimal
    stop_loss: Decimal
    target: Decimal
    exit_time: datetime | None
    exit_price: Decimal | None
    exit_reason: ExitReason
    risk_per_share: Decimal
    r_multiple: Decimal | None
    pnl_per_share: Decimal | None
    quantity: int
    direction: str = "LONG"

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")

        entry_price = _as_decimal(self.entry_price, "entry_price")
        stop_loss = _as_decimal(self.stop_loss, "stop_loss")
        target = _as_decimal(self.target, "target")
        risk_per_share = _as_decimal(self.risk_per_share, "risk_per_share")

        if entry_price <= 0:
            raise ValueError("entry_price must be greater than zero")
        if stop_loss <= 0:
            raise ValueError("stop_loss must be greater than zero")
        if target <= 0:
            raise ValueError("target must be greater than zero")
        if risk_per_share <= 0:
            raise ValueError("risk_per_share must be greater than zero")
        if not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        if self.entry_time < self.setup_time:
            raise ValueError("entry_time must be greater than or equal to setup_time")

        if self.direction == "LONG":
            if stop_loss >= entry_price or entry_price >= target:
                raise ValueError("LONG trade requires stop_loss < entry_price < target")
        else:
            if target >= entry_price or entry_price >= stop_loss:
                raise ValueError("SHORT trade requires target < entry_price < stop_loss")

        exit_time = self.exit_time
        exit_price = _as_decimal(self.exit_price, "exit_price") if self.exit_price is not None else None
        r_multiple = _as_decimal(self.r_multiple, "r_multiple") if self.r_multiple is not None else None
        pnl_per_share = _as_decimal(self.pnl_per_share, "pnl_per_share") if self.pnl_per_share is not None else None

        if exit_price is None:
            if self.exit_reason != ExitReason.OPEN:
                raise ValueError("open trades must use ExitReason.OPEN")
            if exit_time is not None or r_multiple is not None or pnl_per_share is not None:
                raise ValueError("open trades must have no exit_time, r_multiple, or pnl_per_share")
        else:
            if self.exit_reason == ExitReason.OPEN:
                raise ValueError("closed trades must not use ExitReason.OPEN")
            if exit_time is None or r_multiple is None or pnl_per_share is None:
                raise ValueError("closed trades require exit_time, r_multiple, and pnl_per_share")

        object.__setattr__(self, "entry_price", entry_price)
        object.__setattr__(self, "stop_loss", stop_loss)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "risk_per_share", risk_per_share)
        object.__setattr__(self, "exit_price", exit_price)
        object.__setattr__(self, "r_multiple", r_multiple)
        object.__setattr__(self, "pnl_per_share", pnl_per_share)


@dataclass(frozen=True)
class BacktestSummary:
    total_trades: int
    winning_trades: int
    losing_trades: int
    open_trades: int
    win_rate: Decimal
    average_win_r: Decimal
    average_loss_r: Decimal
    expectancy_r: Decimal
    profit_factor: Decimal
    total_r: Decimal
    max_drawdown_r: Decimal
    max_consecutive_losses: int
    average_holding_candles: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "win_rate", _as_decimal(self.win_rate, "win_rate"))
        object.__setattr__(self, "average_win_r", _as_decimal(self.average_win_r, "average_win_r"))
        object.__setattr__(self, "average_loss_r", _as_decimal(self.average_loss_r, "average_loss_r"))
        object.__setattr__(self, "expectancy_r", _as_decimal(self.expectancy_r, "expectancy_r"))
        object.__setattr__(self, "profit_factor", _as_decimal(self.profit_factor, "profit_factor"))
        object.__setattr__(self, "total_r", _as_decimal(self.total_r, "total_r"))
        object.__setattr__(self, "max_drawdown_r", _as_decimal(self.max_drawdown_r, "max_drawdown_r"))
        object.__setattr__(self, "average_holding_candles", _as_decimal(self.average_holding_candles, "average_holding_candles"))


@dataclass(frozen=True)
class PerformanceMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    total_pnl: Decimal
    average_pnl: Decimal
    total_r: Decimal
    average_r: Decimal
    maximum_drawdown: Decimal


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    trades: tuple[BacktestTrade, ...] = field(default_factory=tuple)
    summary: BacktestSummary | None = None
    metrics: PerformanceMetrics | None = None

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if self.start > self.end:
            raise ValueError("start must be less than or equal to end")

        trades_tuple = tuple(self.trades)
        object.__setattr__(self, "trades", trades_tuple)

__all__ = [
    "ExitReason",
    "BacktestTrade",
    "BacktestSummary",
    "PerformanceMetrics",
    "BacktestResult",
]
