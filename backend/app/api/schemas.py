"""Pydantic schemas for API request/response shapes.

Note: these mirror domain types but are API-layer DTOs. No business logic here.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal


class HealthCheck(BaseModel):
    status: str


class InstrumentSchema(BaseModel):
    id: UUID
    symbol: str
    name: Optional[str]
    exchange: Optional[str]


class CandleSchema(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketDataCandleResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None


class ScanRunSchema(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: Optional[datetime]
    universe_date: Optional[datetime]
    universe_version: Optional[str]
    parameters: Optional[Dict[str, Any]]
    result_count: int
    metadata: Optional[Dict[str, Any]]


class MarketDataIngestRequest(BaseModel):
    symbol: str
    timeframe: str
    start: datetime
    end: datetime


class MarketDataIngestResponse(BaseModel):
    symbol: str
    timeframe: str
    candles_fetched: int
    candles_persisted: int
    status: str


class StrategyEvaluationRequest(BaseModel):
    symbol: str
    timeframe: str
    start: datetime
    end: datetime


class StrategyCandidateResponse(BaseModel):
    symbol: str
    timeframe: str
    direction: str
    entry_price: Decimal
    stop_loss: Decimal
    target: Decimal
    risk_per_share: Decimal
    reward: Decimal
    risk_reward_ratio: Decimal
    setup_name: str


class StrategyEvidenceResponse(BaseModel):
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


class StrategyEvaluationResponse(BaseModel):
    has_setup: bool
    candidate: StrategyCandidateResponse | None = None
    evidence: StrategyEvidenceResponse | None = None
    status: str
    reason: str | None = None


class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    account_equity: Decimal = Field(gt=Decimal("0"))
    risk_percent: Decimal = Field(gt=Decimal("0"))


class BacktestTradeResponse(BaseModel):
    symbol: str
    timeframe: str
    direction: str
    setup_time: datetime
    entry_time: datetime
    entry_price: Decimal
    stop_loss: Decimal
    target: Decimal
    exit_time: datetime
    exit_price: Decimal
    quantity: int
    risk_per_share: Decimal
    risk_amount: Decimal
    pnl: Decimal
    exit_reason: str


class BacktestResponse(BaseModel):
    symbol: str
    timeframe: str
    completed_trades: int
    trades: list[BacktestTradeResponse]
