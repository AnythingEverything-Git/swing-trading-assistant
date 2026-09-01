"""Domain strategy contract and the concrete Breakout → Retest → Confirmation strategy.

This module intentionally keeps strategy logic inside the domain boundary without
access to repositories, providers, database access, or API layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping, Protocol, Sequence

from app.application.market_data.indicators import atr, volume_sma
from app.domain.market_data import Candle

Direction = Literal["LONG", "SHORT"]


def _as_decimal(value: Decimal | int | float | str, field_name: str) -> Decimal:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal value") from exc
    if decimal_value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return decimal_value


@dataclass(frozen=True)
class StrategyInput:
    symbol: str
    timeframe: str
    candles: Sequence[Candle]
    indicator_values: Mapping[str, Decimal | None] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if not self.candles:
            raise ValueError("candles must contain at least one value")
        for idx in range(1, len(self.candles)):
            prev = self.candles[idx - 1].timestamp
            current = self.candles[idx].timestamp
            if current < prev:
                raise ValueError("candles must be ordered chronologically")


@dataclass(frozen=True)
class TradeCandidate:
    symbol: str
    timeframe: str
    direction: Direction
    entry_price: Decimal
    stop_loss: Decimal
    target: Decimal
    risk_per_share: Decimal
    reward: Decimal
    risk_reward_ratio: Decimal
    setup_name: str

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

        if self.direction == "LONG":
            if stop_loss >= entry_price:
                raise ValueError("LONG trade requires stop_loss < entry_price")
            if target <= entry_price:
                raise ValueError("LONG trade requires target > entry_price")
        else:
            if stop_loss <= entry_price:
                raise ValueError("SHORT trade requires stop_loss > entry_price")
            if target >= entry_price:
                raise ValueError("SHORT trade requires target < entry_price")

        risk = abs(entry_price - stop_loss)
        reward_value = abs(target - entry_price)
        rr_ratio = reward_value / risk

        object.__setattr__(self, "entry_price", entry_price)
        object.__setattr__(self, "stop_loss", stop_loss)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "risk_per_share", risk)
        object.__setattr__(self, "reward", reward_value)
        object.__setattr__(self, "risk_reward_ratio", rr_ratio)


@dataclass(frozen=True)
class StrategyEvidence:
    resistance: Decimal
    breakout_candle_index: int
    breakout_candle_time: datetime
    retest_candle_index: int
    retest_candle_time: datetime
    confirmation_candle_index: int
    confirmation_candle_time: datetime
    atr_value: Decimal
    volume_sma_value: Decimal
    breakout_volume: int | None
    retest_low: Decimal
    confirmation_volume: int | None
    decision: str


@dataclass(frozen=True)
class StrategyResult:
    has_setup: bool
    candidate: TradeCandidate | None = None
    evidence: StrategyEvidence | None = None
    status: str = "NO_SETUP"
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.has_setup and self.candidate is None:
            raise ValueError("candidate is required when has_setup is True")
        if not self.has_setup and self.candidate is not None:
            raise ValueError("candidate must be None when has_setup is False")
        if self.has_setup and self.evidence is not None and self.status == "NO_SETUP":
            object.__setattr__(self, "status", "VALID_SETUP")
        if not self.has_setup and self.evidence is not None:
            raise ValueError("evidence must be None when has_setup is False")
        if not self.has_setup and not self.status:
            object.__setattr__(self, "status", "NO_SETUP")


class Strategy(Protocol):
    def evaluate(self, strategy_input: StrategyInput) -> StrategyResult:  # pragma: no cover - interface
        """Evaluate the input candles and return a deterministic strategy result."""


class BreakoutRetestConfirmationStrategy:
    """Deterministic breakout strategy using a confirmed swing high, retest, and confirmation sequence."""

    atr_period = 14
    volume_sma_period = 20
    max_retest_window = 5
    max_confirmation_window = 3

    def _is_confirmed_swing_high(self, candles: Sequence[Candle], index: int) -> bool:
        if index < 2 or index >= len(candles) - 2:
            return False
        current = candles[index]
        prev_1 = candles[index - 1]
        prev_2 = candles[index - 2]
        next_1 = candles[index + 1]
        next_2 = candles[index + 2]
        return (
            current.high > prev_1.high
            and current.high > prev_2.high
            and current.high >= next_1.high
            and current.high >= next_2.high
        )

    def _is_confirmed_swing_low(self, candles: Sequence[Candle], index: int) -> bool:
        if index < 2 or index >= len(candles) - 2:
            return False
        current = candles[index]
        prev_1 = candles[index - 1]
        prev_2 = candles[index - 2]
        next_1 = candles[index + 1]
        next_2 = candles[index + 2]
        return (
            current.low < prev_1.low
            and current.low < prev_2.low
            and current.low <= next_1.low
            and current.low <= next_2.low
        )

    def _calculate_atr_values(self, candles: Sequence[Candle]) -> list[Decimal | None]:
        return atr(candles, self.atr_period)

    def _calculate_volume_sma_values(self, candles: Sequence[Candle]) -> list[Decimal | None]:
        return volume_sma(candles, self.volume_sma_period)

    def evaluate(self, strategy_input: StrategyInput) -> StrategyResult:
        candles = list(strategy_input.candles)
        if len(candles) < 20:
            return StrategyResult(has_setup=False, status="NO_SETUP", reason="insufficient historical candles")

        atr_values = self._calculate_atr_values(candles)
        volume_sma_values = self._calculate_volume_sma_values(candles)

        for breakout_index in range(2, len(candles) - 2):
            resistance_index = None
            resistance = None
            for idx in range(2, breakout_index - 1):
                if self._is_confirmed_swing_high(candles, idx):
                    resistance_index = idx
                    resistance = candles[idx].high

            if resistance is None or resistance_index is None:
                continue

            atr_value = atr_values[breakout_index]
            volume_sma_value = volume_sma_values[breakout_index]
            candle = candles[breakout_index]
            if atr_value is None or volume_sma_value is None:
                continue
            if candle.close <= resistance + (Decimal("0.10") * atr_value):
                continue
            if candle.volume is None or volume_sma_value <= 0:
                continue
            if candle.volume < (Decimal("1.5") * volume_sma_value):
                continue

            retest_index = None
            retest_low = None
            for candidate_index in range(breakout_index + 1, min(len(candles), breakout_index + 1 + self.max_retest_window)):
                candidate = candles[candidate_index]
                candidate_atr = atr_values[candidate_index]
                if candidate_atr is None:
                    continue
                if candidate.close < resistance - (Decimal("0.20") * candidate_atr):
                    retest_index = None
                    retest_low = None
                    break
                if candidate.low <= resistance + (Decimal("0.20") * candidate_atr) and candidate.close >= resistance:
                    retest_index = candidate_index
                    retest_low = candidate.low
                    break

            if retest_index is None or retest_low is None:
                continue

            confirmation_index = None
            confirmation_limit = min(len(candles), retest_index + self.max_confirmation_window + 1)
            for candidate_index in range(retest_index + 1, confirmation_limit):
                candidate = candles[candidate_index]
                candidate_sma = volume_sma_values[candidate_index]
                if candidate_sma is None:
                    continue
                if candidate.close <= candles[candidate_index - 1].high:
                    continue
                if candidate.close <= resistance:
                    continue
                if candidate.volume is None:
                    continue
                if candidate.volume < candidate_sma:
                    continue
                confirmation_index = candidate_index
                break

            if confirmation_index is None:
                continue

            confirmation_candle = candles[confirmation_index]
            if confirmation_candle.volume is None:
                continue
            if confirmation_candle.volume < volume_sma_values[confirmation_index] if volume_sma_values[confirmation_index] is not None else Decimal("0"):
                continue

            entry_price = confirmation_candle.close
            retest_atr = atr_values[retest_index]
            if retest_atr is None:
                continue
            atr_stop = resistance - retest_atr
            stop_loss = min(retest_low, atr_stop)
            if entry_price <= stop_loss:
                continue

            risk = entry_price - stop_loss
            if risk <= 0:
                continue
            if (entry_price - stop_loss) / entry_price > Decimal("0.05"):
                continue

            target_price = entry_price + (Decimal("2.0") * risk)
            reward = target_price - entry_price
            rr_ratio = reward / risk
            if reward <= 0 or rr_ratio < Decimal("2.0"):
                continue

            candidate = TradeCandidate(
                symbol=strategy_input.symbol,
                timeframe=strategy_input.timeframe,
                direction="LONG",
                entry_price=entry_price,
                stop_loss=stop_loss,
                target=target_price,
                risk_per_share=risk,
                reward=reward,
                risk_reward_ratio=rr_ratio,
                setup_name="BreakoutRetestConfirmation",
            )

            evidence = StrategyEvidence(
                resistance=resistance,
                breakout_candle_index=breakout_index,
                breakout_candle_time=candle.timestamp,
                retest_candle_index=retest_index,
                retest_candle_time=candles[retest_index].timestamp,
                confirmation_candle_index=confirmation_index,
                confirmation_candle_time=confirmation_candle.timestamp,
                atr_value=atr_value,
                volume_sma_value=volume_sma_value,
                breakout_volume=candle.volume,
                retest_low=retest_low,
                confirmation_volume=confirmation_candle.volume,
                decision="valid breakout -> retest -> confirmation",
            )

            result = StrategyResult(
                has_setup=True,
                candidate=candidate,
                evidence=evidence,
                status="VALID_SETUP",
                reason="valid breakout retest confirmation",
            )
            return result

        return StrategyResult(has_setup=False, status="NO_SETUP", reason="no valid setup")
