from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.application.backtesting.backtest_models import BacktestResult, BacktestTrade, ExitReason
from app.application.backtesting.performance_metrics import calculate_performance_metrics
from app.application.backtesting.position_sizing import calculate_position_size
from app.domain.market_data import Candle
from app.domain.market_data.provider import MarketDataProvider
from app.domain.strategy.strategy import Strategy, StrategyInput


class BacktestService:
    def __init__(self, market_data_provider: MarketDataProvider, strategy: Strategy) -> None:
        self.market_data_provider = market_data_provider
        self.strategy = strategy

    async def run(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        account_equity: Decimal,
        risk_percent: Decimal,
        slippage_per_share: Decimal = Decimal("0"),
        cost_per_trade: Decimal = Decimal("0"),
    ) -> BacktestResult:
        if start > end:
            raise ValueError("start must be less than or equal to end")

        candles = await self.market_data_provider.get_candles(symbol, timeframe, start, end)
        trades = self._simulate(
            symbol,
            timeframe,
            candles,
            account_equity,
            risk_percent,
            slippage_per_share,
            cost_per_trade,
        )
        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            trades=trades,
            metrics=calculate_performance_metrics(trades, account_equity),
        )

    def _simulate(
        self,
        symbol: str,
        timeframe: str,
        candles: list[Candle],
        account_equity: Decimal,
        risk_percent: Decimal,
        slippage_per_share: Decimal,
        cost_per_trade: Decimal,
    ) -> tuple[BacktestTrade, ...]:
        trades: list[BacktestTrade] = []
        cursor = 0
        current_equity = account_equity

        while cursor < len(candles):
            result = self.strategy.evaluate(
                StrategyInput(symbol=symbol, timeframe=timeframe, candles=candles[: cursor + 1])
            )
            if not result.has_setup or result.candidate is None or result.evidence is None:
                cursor += 1
                continue

            candidate = result.candidate
            if result.evidence.confirmation_candle_index != cursor:
                cursor += 1
                continue
            if cursor == len(candles) - 1:
                cursor += 1
                continue
            sizing = calculate_position_size(current_equity, risk_percent, candidate)
            if sizing.quantity == 0:
                cursor += 1
                continue

            confirmation_index = result.evidence.confirmation_candle_index
            if confirmation_index >= len(candles):
                cursor += 1
                continue

            exit_index, raw_exit_price, exit_reason = self._find_exit(
                candles,
                confirmation_index,
                candidate.stop_loss,
                candidate.target,
                candidate.direction,
            )
            if candidate.direction == "LONG":
                entry_fill = candidate.entry_price + slippage_per_share
                if not (candidate.stop_loss < entry_fill < candidate.target):
                    cursor += 1
                    continue
                exit_fill = raw_exit_price - slippage_per_share
                gross_pnl = (exit_fill - entry_fill) * Decimal(sizing.quantity)
            else:
                entry_fill = candidate.entry_price - slippage_per_share
                if not (candidate.target < entry_fill < candidate.stop_loss):
                    cursor += 1
                    continue
                exit_fill = raw_exit_price + slippage_per_share
                gross_pnl = (entry_fill - exit_fill) * Decimal(sizing.quantity)

            quantity = sizing.quantity
            net_pnl = gross_pnl - cost_per_trade
            pnl_per_share = net_pnl / Decimal(quantity)
            r_multiple = pnl_per_share / candidate.risk_per_share
            trades.append(
                BacktestTrade(
                    symbol=candidate.symbol,
                    timeframe=candidate.timeframe,
                    setup_time=result.evidence.breakout_candle_time,
                    entry_time=candles[confirmation_index].timestamp,
                    entry_price=entry_fill,
                    stop_loss=candidate.stop_loss,
                    target=candidate.target,
                    exit_time=candles[exit_index].timestamp,
                    exit_price=exit_fill,
                    exit_reason=exit_reason,
                    risk_per_share=candidate.risk_per_share,
                    r_multiple=r_multiple,
                    pnl_per_share=pnl_per_share,
                    quantity=quantity,
                    direction=candidate.direction,
                )
            )
            current_equity += net_pnl
            cursor = exit_index + 1

        return tuple(trades)

    @staticmethod
    def _find_exit(
        candles: list[Candle],
        confirmation_index: int,
        stop_loss: Decimal,
        target: Decimal,
        direction: str = "LONG",
    ) -> tuple[int, Decimal, ExitReason]:
        for index in range(confirmation_index + 1, len(candles)):
            candle = candles[index]
            if direction == "SHORT":
                if candle.open >= stop_loss:
                    return index, candle.open, ExitReason.GAP_THROUGH_STOP
                if candle.open <= target:
                    return index, candle.open, ExitReason.GAP_THROUGH_TARGET
                if candle.high >= stop_loss:
                    return index, stop_loss, ExitReason.STOP_LOSS
                if candle.low <= target:
                    return index, target, ExitReason.TARGET
            else:
                if candle.open <= stop_loss:
                    return index, candle.open, ExitReason.GAP_THROUGH_STOP
                if candle.open >= target:
                    return index, candle.open, ExitReason.GAP_THROUGH_TARGET
                if candle.low <= stop_loss:
                    return index, stop_loss, ExitReason.STOP_LOSS
                if candle.high >= target:
                    return index, target, ExitReason.TARGET

        final_index = len(candles) - 1
        return final_index, candles[final_index].close, ExitReason.END_OF_DATA


__all__ = ["BacktestService"]
