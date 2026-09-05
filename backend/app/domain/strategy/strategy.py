"""Domain strategy contract and Breakout/Breakdown → Retest → Confirmation.

LONG: swing-high resistance → volume breakout → retest → last-bar confirmation.
SHORT: swing-low support → volume breakdown → retest → last-bar confirmation.

Identical windows, ATR/volume thresholds, risk filters, and NOW contract for both.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping, Protocol, Sequence

from app.domain.market_data.indicators import atr, volume_sma
from app.domain.market_data import Candle

Direction = Literal["LONG", "SHORT"]
FormingStage = Literal["AWAITING_RETEST", "AWAITING_CONFIRMATION"]


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


def _as_decimal_strict(value: Decimal, field_name: str, *, positive: bool = True) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return value


@dataclass(frozen=True)
class StrategyEvidence:
    """Structure evidence for a confirmed setup.

    Field semantics by direction:
    - LONG: ``resistance`` = swing-high level; ``retest_low`` = retest wick low
    - SHORT: ``resistance`` stores support (swing-low level); ``retest_low`` stores retest wick high
      (legacy field names kept for API stability; use ``direction`` and helper properties)
    """

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
    direction: Direction = "LONG"

    @property
    def structure_level(self) -> Decimal:
        return self.resistance

    @property
    def retest_extreme(self) -> Decimal:
        return self.retest_low

    @property
    def support(self) -> Decimal:
        if self.direction != "SHORT":
            raise AttributeError("support is only defined for SHORT evidence")
        return self.resistance

    @property
    def retest_high(self) -> Decimal:
        if self.direction != "SHORT":
            raise AttributeError("retest_high is only defined for SHORT evidence")
        return self.retest_low

    def __post_init__(self) -> None:
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if not isinstance(self.breakout_candle_time, datetime):
            raise TypeError("breakout_candle_time must be a datetime")
        if not isinstance(self.retest_candle_time, datetime):
            raise TypeError("retest_candle_time must be a datetime")
        if not isinstance(self.confirmation_candle_time, datetime):
            raise TypeError("confirmation_candle_time must be a datetime")

        for field_name, value in (
            ("resistance", self.resistance),
            ("atr_value", self.atr_value),
            ("volume_sma_value", self.volume_sma_value),
            ("retest_low", self.retest_low),
        ):
            object.__setattr__(self, field_name, _as_decimal_strict(value, field_name, positive=True))

        for field_name, value in (
            ("breakout_candle_index", self.breakout_candle_index),
            ("retest_candle_index", self.retest_candle_index),
            ("confirmation_candle_index", self.confirmation_candle_index),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")

        for field_name, value in (
            ("breakout_volume", self.breakout_volume),
            ("confirmation_volume", self.confirmation_volume),
        ):
            if value is not None:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{field_name} must be None or a non-negative integer")

        if not isinstance(self.decision, str) or not self.decision.strip():
            raise ValueError("decision must be a non-empty string")


@dataclass(frozen=True)
class StrategyResult:
    has_setup: bool
    candidate: TradeCandidate | None = None
    evidence: StrategyEvidence | None = None
    status: str = "NO_SETUP"
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.has_setup:
            if self.candidate is None:
                raise ValueError("candidate is required when has_setup is True")
            if self.evidence is None:
                raise ValueError("evidence is required when has_setup is True")
            if self.candidate.direction != self.evidence.direction:
                raise ValueError("candidate.direction must match evidence.direction")
            if self.status == "NO_SETUP":
                object.__setattr__(self, "status", "VALID_SETUP")
        else:
            if self.candidate is not None:
                raise ValueError("candidate must be None when has_setup is False")
            if self.evidence is not None:
                raise ValueError("evidence must be None when has_setup is False")
        if not self.has_setup and not self.status:
            object.__setattr__(self, "status", "NO_SETUP")


@dataclass(frozen=True)
class FormingSetup:
    """Incomplete sequence still inside its retest or confirmation window.

    Never carries Entry / SL / Target. Those exist only after last-bar confirmation.
    For SHORT, ``resistance`` holds support and ``retest_low`` holds retest high.
    """

    symbol: str
    timeframe: str
    stage: FormingStage
    resistance: Decimal
    breakout_candle_index: int
    breakout_candle_time: datetime
    breakout_volume: int | None
    atr_value: Decimal
    volume_sma_value: Decimal
    bars_elapsed: int
    bars_remaining: int
    reason: str
    retest_candle_index: int | None = None
    retest_candle_time: datetime | None = None
    retest_low: Decimal | None = None
    direction: Direction = "LONG"

    def __post_init__(self) -> None:
        if self.stage not in {"AWAITING_RETEST", "AWAITING_CONFIRMATION"}:
            raise ValueError("stage must be AWAITING_RETEST or AWAITING_CONFIRMATION")
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if self.bars_elapsed < 0 or self.bars_remaining < 0:
            raise ValueError("bars_elapsed and bars_remaining must be non-negative")
        object.__setattr__(self, "resistance", _as_decimal_strict(self.resistance, "resistance", positive=True))
        object.__setattr__(self, "atr_value", _as_decimal_strict(self.atr_value, "atr_value", positive=True))
        object.__setattr__(
            self,
            "volume_sma_value",
            _as_decimal_strict(self.volume_sma_value, "volume_sma_value", positive=True),
        )
        if self.stage == "AWAITING_CONFIRMATION":
            if self.retest_candle_index is None or self.retest_candle_time is None or self.retest_low is None:
                raise ValueError("AWAITING_CONFIRMATION requires retest fields")
            object.__setattr__(
                self,
                "retest_low",
                _as_decimal_strict(self.retest_low, "retest_low", positive=True),
            )


class Strategy(Protocol):
    def evaluate(self, strategy_input: StrategyInput) -> StrategyResult:  # pragma: no cover - interface
        """Evaluate the input candles and return a deterministic strategy result."""


class BreakoutRetestConfirmationStrategy:
    """Deterministic breakout (LONG) and breakdown (SHORT) strategy.

    Shared contract:
    - ATR period 14, volume SMA 20
    - Retest window ≤ 5 bars after breakout/breakdown
    - Confirmation window ≤ 3 bars after retest
    - Confirmation must be on the final candle (NOW)
    - Stop distance ≤ 5% of entry; target exactly 2R
    """

    atr_period = 14
    volume_sma_period = 20
    max_retest_window = 5
    max_confirmation_window = 3
    breakout_atr_buffer = Decimal("0.10")
    retest_atr_buffer = Decimal("0.20")
    breakout_volume_multiple = Decimal("1.5")
    max_risk_fraction = Decimal("0.05")
    target_rr = Decimal("2.0")

    def _recent_breakout_start(self, candle_count: int) -> int:
        """Only breakouts that can still confirm/form near the last bar matter for NOW.

        Confirmation must land on the final candle; retest+confirmation windows are
        short, so older breakouts cannot produce a valid NOW setup or forming state.
        """
        # +2 covers swing confirmation lookaround used by structure helpers.
        lookback = self.max_retest_window + self.max_confirmation_window + 2
        return max(2, candle_count - lookback - 1)

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

    def _structure_level(
        self,
        candles: Sequence[Candle],
        breakout_index: int,
        direction: Direction,
    ) -> Decimal | None:
        level: Decimal | None = None
        for idx in range(2, breakout_index - 1):
            if direction == "LONG":
                if self._is_confirmed_swing_high(candles, idx):
                    level = candles[idx].high
            else:
                if self._is_confirmed_swing_low(candles, idx):
                    level = candles[idx].low
        return level

    def _is_breakout(
        self,
        candle: Candle,
        level: Decimal,
        atr_value: Decimal,
        volume_sma_value: Decimal,
        direction: Direction,
    ) -> bool:
        if candle.volume is None or volume_sma_value <= 0:
            return False
        if candle.volume < (self.breakout_volume_multiple * volume_sma_value):
            return False
        buffer = self.breakout_atr_buffer * atr_value
        if direction == "LONG":
            return candle.close > level + buffer
        return candle.close < level - buffer

    def _find_retest(
        self,
        candles: Sequence[Candle],
        atr_values: Sequence[Decimal | None],
        breakout_index: int,
        level: Decimal,
        direction: Direction,
    ) -> tuple[int | None, Decimal | None, bool]:
        """Return (retest_index, retest_extreme, invalidated)."""
        retest_index: int | None = None
        retest_extreme: Decimal | None = None
        retest_limit = min(len(candles), breakout_index + 1 + self.max_retest_window)
        for candidate_index in range(breakout_index + 1, retest_limit):
            candidate = candles[candidate_index]
            candidate_atr = atr_values[candidate_index]
            if candidate_atr is None:
                continue
            buffer = self.retest_atr_buffer * candidate_atr
            if direction == "LONG":
                if candidate.close < level - buffer:
                    return None, None, True
                if candidate.low <= level + buffer and candidate.close >= level:
                    return candidate_index, candidate.low, False
            else:
                if candidate.close > level + buffer:
                    return None, None, True
                if candidate.high >= level - buffer and candidate.close <= level:
                    return candidate_index, candidate.high, False
        return retest_index, retest_extreme, False

    def _find_confirmation(
        self,
        candles: Sequence[Candle],
        volume_sma_values: Sequence[Decimal | None],
        retest_index: int,
        level: Decimal,
        direction: Direction,
    ) -> int | None:
        confirmation_limit = min(len(candles), retest_index + self.max_confirmation_window + 1)
        for candidate_index in range(retest_index + 1, confirmation_limit):
            candidate = candles[candidate_index]
            candidate_sma = volume_sma_values[candidate_index]
            if candidate_sma is None or candidate.volume is None:
                continue
            if candidate.volume < candidate_sma:
                continue
            prior = candles[candidate_index - 1]
            if direction == "LONG":
                if candidate.close <= prior.high:
                    continue
                if candidate.close <= level:
                    continue
            else:
                if candidate.close >= prior.low:
                    continue
                if candidate.close >= level:
                    continue
            return candidate_index
        return None

    def _build_candidate(
        self,
        strategy_input: StrategyInput,
        candles: Sequence[Candle],
        atr_values: Sequence[Decimal | None],
        volume_sma_values: Sequence[Decimal | None],
        direction: Direction,
        level: Decimal,
        breakout_index: int,
        retest_index: int,
        retest_extreme: Decimal,
        confirmation_index: int,
    ) -> StrategyResult | None:
        confirmation_candle = candles[confirmation_index]
        breakout_candle = candles[breakout_index]
        atr_value = atr_values[breakout_index]
        volume_sma_value = volume_sma_values[breakout_index]
        retest_atr = atr_values[retest_index]
        confirm_sma = volume_sma_values[confirmation_index]
        if (
            atr_value is None
            or volume_sma_value is None
            or retest_atr is None
            or confirm_sma is None
            or confirmation_candle.volume is None
        ):
            return None
        if confirmation_candle.volume < confirm_sma:
            return None

        entry_price = confirmation_candle.close
        if direction == "LONG":
            atr_stop = level - retest_atr
            stop_loss = min(retest_extreme, atr_stop)
            if entry_price <= stop_loss:
                return None
            risk = entry_price - stop_loss
            if risk <= 0 or risk / entry_price > self.max_risk_fraction:
                return None
            target_price = entry_price + (self.target_rr * risk)
            decision = "valid breakout -> retest -> confirmation"
            reason = "valid breakout retest confirmation"
            setup_name = "BreakoutRetestConfirmation"
        else:
            atr_stop = level + retest_atr
            stop_loss = max(retest_extreme, atr_stop)
            if entry_price >= stop_loss:
                return None
            risk = stop_loss - entry_price
            if risk <= 0 or risk / entry_price > self.max_risk_fraction:
                return None
            target_price = entry_price - (self.target_rr * risk)
            decision = "valid breakdown -> retest -> confirmation"
            reason = "valid breakdown retest confirmation"
            setup_name = "BreakdownRetestConfirmation"

        reward = abs(target_price - entry_price)
        rr_ratio = reward / risk
        if reward <= 0 or rr_ratio < self.target_rr:
            return None

        candidate = TradeCandidate(
            symbol=strategy_input.symbol,
            timeframe=strategy_input.timeframe,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target_price,
            risk_per_share=risk,
            reward=reward,
            risk_reward_ratio=rr_ratio,
            setup_name=setup_name,
        )
        evidence = StrategyEvidence(
            resistance=level,
            breakout_candle_index=breakout_index,
            breakout_candle_time=breakout_candle.timestamp,
            retest_candle_index=retest_index,
            retest_candle_time=candles[retest_index].timestamp,
            confirmation_candle_index=confirmation_index,
            confirmation_candle_time=confirmation_candle.timestamp,
            atr_value=atr_value,
            volume_sma_value=volume_sma_value,
            breakout_volume=breakout_candle.volume,
            retest_low=retest_extreme,
            confirmation_volume=confirmation_candle.volume,
            decision=decision,
            direction=direction,
        )
        return StrategyResult(
            has_setup=True,
            candidate=candidate,
            evidence=evidence,
            status="VALID_SETUP",
            reason=reason,
        )

    def _evaluate_direction(
        self,
        strategy_input: StrategyInput,
        candles: list[Candle],
        atr_values: list[Decimal | None],
        volume_sma_values: list[Decimal | None],
        direction: Direction,
    ) -> StrategyResult:
        for breakout_index in range(self._recent_breakout_start(len(candles)), len(candles) - 2):
            level = self._structure_level(candles, breakout_index, direction)
            if level is None:
                continue
            atr_value = atr_values[breakout_index]
            volume_sma_value = volume_sma_values[breakout_index]
            candle = candles[breakout_index]
            if atr_value is None or volume_sma_value is None:
                continue
            if not self._is_breakout(candle, level, atr_value, volume_sma_value, direction):
                continue

            retest_index, retest_extreme, invalidated = self._find_retest(
                candles, atr_values, breakout_index, level, direction
            )
            if invalidated or retest_index is None or retest_extreme is None:
                continue

            confirmation_index = self._find_confirmation(
                candles, volume_sma_values, retest_index, level, direction
            )
            if confirmation_index is None:
                continue
            if confirmation_index != len(candles) - 1:
                continue

            built = self._build_candidate(
                strategy_input,
                candles,
                atr_values,
                volume_sma_values,
                direction,
                level,
                breakout_index,
                retest_index,
                retest_extreme,
                confirmation_index,
            )
            if built is not None:
                return built

        return StrategyResult(has_setup=False, status="NO_SETUP", reason="no valid setup")

    @staticmethod
    def _prefer_result(left: StrategyResult, right: StrategyResult) -> StrategyResult:
        if left.has_setup and right.has_setup:
            assert left.evidence is not None and right.evidence is not None
            if left.evidence.breakout_candle_index != right.evidence.breakout_candle_index:
                return left if left.evidence.breakout_candle_index > right.evidence.breakout_candle_index else right
            # Same breakout bar cannot be both; fall back to LONG preference for determinism.
            return left if left.candidate and left.candidate.direction == "LONG" else right
        if left.has_setup:
            return left
        if right.has_setup:
            return right
        return StrategyResult(has_setup=False, status="NO_SETUP", reason="no valid setup")

    def evaluate(self, strategy_input: StrategyInput) -> StrategyResult:
        candles = list(strategy_input.candles)
        if len(candles) < 20:
            return StrategyResult(has_setup=False, status="NO_SETUP", reason="insufficient historical candles")

        atr_values = self._calculate_atr_values(candles)
        volume_sma_values = self._calculate_volume_sma_values(candles)
        long_result = self._evaluate_direction(
            strategy_input, candles, atr_values, volume_sma_values, "LONG"
        )
        short_result = self._evaluate_direction(
            strategy_input, candles, atr_values, volume_sma_values, "SHORT"
        )
        return self._prefer_result(long_result, short_result)

    def _inspect_forming_direction(
        self,
        strategy_input: StrategyInput,
        candles: list[Candle],
        atr_values: list[Decimal | None],
        volume_sma_values: list[Decimal | None],
        direction: Direction,
    ) -> FormingSetup | None:
        last_index = len(candles) - 1
        latest: FormingSetup | None = None

        for breakout_index in range(self._recent_breakout_start(len(candles)), len(candles)):
            level = self._structure_level(candles, breakout_index, direction)
            if level is None:
                continue
            atr_value = atr_values[breakout_index]
            volume_sma_value = volume_sma_values[breakout_index]
            candle = candles[breakout_index]
            if atr_value is None or volume_sma_value is None:
                continue
            if not self._is_breakout(candle, level, atr_value, volume_sma_value, direction):
                continue

            retest_index, retest_extreme, invalidated = self._find_retest(
                candles, atr_values, breakout_index, level, direction
            )
            if invalidated:
                continue

            if retest_index is None or retest_extreme is None:
                elapsed = last_index - breakout_index
                if elapsed < 0 or elapsed > self.max_retest_window:
                    continue
                reason = (
                    "volume breakout in place; retest window still open"
                    if direction == "LONG"
                    else "volume breakdown in place; retest window still open"
                )
                latest = FormingSetup(
                    symbol=strategy_input.symbol,
                    timeframe=strategy_input.timeframe,
                    stage="AWAITING_RETEST",
                    resistance=level,
                    breakout_candle_index=breakout_index,
                    breakout_candle_time=candle.timestamp,
                    breakout_volume=candle.volume,
                    atr_value=atr_value,
                    volume_sma_value=volume_sma_value,
                    bars_elapsed=elapsed,
                    bars_remaining=self.max_retest_window - elapsed,
                    reason=reason,
                    direction=direction,
                )
                continue

            confirmation_index = self._find_confirmation(
                candles, volume_sma_values, retest_index, level, direction
            )
            if confirmation_index is not None:
                continue

            elapsed = last_index - retest_index
            if elapsed < 0 or elapsed > self.max_confirmation_window:
                continue
            reason = (
                "retest complete; waiting for confirmation close above resistance"
                if direction == "LONG"
                else "retest complete; waiting for confirmation close below support"
            )
            latest = FormingSetup(
                symbol=strategy_input.symbol,
                timeframe=strategy_input.timeframe,
                stage="AWAITING_CONFIRMATION",
                resistance=level,
                breakout_candle_index=breakout_index,
                breakout_candle_time=candle.timestamp,
                breakout_volume=candle.volume,
                atr_value=atr_value,
                volume_sma_value=volume_sma_value,
                bars_elapsed=elapsed,
                bars_remaining=self.max_confirmation_window - elapsed,
                reason=reason,
                retest_candle_index=retest_index,
                retest_candle_time=candles[retest_index].timestamp,
                retest_low=retest_extreme,
                direction=direction,
            )

        return latest

    @staticmethod
    def _prefer_forming(left: FormingSetup | None, right: FormingSetup | None) -> FormingSetup | None:
        if left is None:
            return right
        if right is None:
            return left
        stage_rank = {"AWAITING_CONFIRMATION": 1, "AWAITING_RETEST": 0}
        if stage_rank[left.stage] != stage_rank[right.stage]:
            return left if stage_rank[left.stage] > stage_rank[right.stage] else right
        if left.breakout_candle_index != right.breakout_candle_index:
            return left if left.breakout_candle_index > right.breakout_candle_index else right
        return left if left.direction == "LONG" else right

    def inspect_forming(
        self,
        strategy_input: StrategyInput,
        *,
        evaluated: StrategyResult | None = None,
    ) -> FormingSetup | None:
        """Return an in-progress setup near the last bar, or None.

        Does not change the NOW contract: last-bar confirmation remains ``evaluate()``.
        If ``evaluate()`` already yields a valid setup, forming is None.

        Pass ``evaluated`` to avoid a second full evaluate when the caller already ran it.
        """
        result = evaluated if evaluated is not None else self.evaluate(strategy_input)
        if result.has_setup:
            return None

        candles = list(strategy_input.candles)
        if len(candles) < 20:
            return None

        atr_values = self._calculate_atr_values(candles)
        volume_sma_values = self._calculate_volume_sma_values(candles)
        long_forming = self._inspect_forming_direction(
            strategy_input, candles, atr_values, volume_sma_values, "LONG"
        )
        short_forming = self._inspect_forming_direction(
            strategy_input, candles, atr_values, volume_sma_values, "SHORT"
        )
        return self._prefer_forming(long_forming, short_forming)
