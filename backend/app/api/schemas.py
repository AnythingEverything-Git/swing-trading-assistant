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
    id: int
    started_at: datetime
    finished_at: Optional[datetime]
    universe_date: Optional[datetime]
    universe_version: Optional[str]
    parameters: Optional[Dict[str, Any]]
    result_count: int
    metadata: Optional[Dict[str, Any]]
    result_payload: Optional[Dict[str, Any]] = None


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


class OpportunityScanRequest(BaseModel):
    timeframe: str
    start: datetime
    end: datetime
    universe: str = Field(
        default="NIFTY_500",
        description="Index universe to scan: NIFTY_50, NIFTY_100, NIFTY_200, or NIFTY_500.",
    )
    account_equity: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
        description="Optional account equity for position sizing on each eligible.",
    )
    risk_percent: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    top_n: int = Field(default=5, ge=1, le=50)
    min_score: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))


class EligibleOpportunityResponse(BaseModel):
    symbol: str
    candidate: StrategyCandidateResponse
    evidence: StrategyEvidenceResponse
    quality_score: Decimal | None = None
    rank: int | None = None
    quantity: int | None = None
    risk_amount: Decimal | None = None
    narrative: str | None = None
    invalidation: str | None = None
    quality_reason: str | None = None
    current_price: Decimal | None = None
    current_price_change_percent: Decimal | None = None


class FormingSetupResponse(BaseModel):
    symbol: str
    timeframe: str
    stage: str
    resistance: Decimal
    breakout_candle_index: int
    breakout_candle_time: datetime
    breakout_volume: int | None
    atr_value: Decimal
    volume_sma_value: Decimal
    bars_elapsed: int
    bars_remaining: int
    reason: str
    narrative: str | None = None
    retest_candle_index: int | None = None
    retest_candle_time: datetime | None = None
    retest_low: Decimal | None = None
    current_price: Decimal | None = None
    current_price_change_percent: Decimal | None = None


class OpportunityScanResponse(BaseModel):
    universe_name: str
    universe_version: str
    timeframe: str
    start: datetime
    end: datetime
    symbols_scanned: int
    eligible_count: int
    no_setup_count: int
    unavailable_count: int = 0
    error_count: int = 0
    opportunities: list[EligibleOpportunityResponse]
    issues: list["ScanIssueResponse"] = []
    scan_run_id: int | None = None
    forming_count: int = 0
    forming: list[FormingSetupResponse] = []
    top: list[EligibleOpportunityResponse] = []
    data_source: str = "demo"
    data_claim: str = "Demo candles — not live market data"
    last_candle_time: datetime | None = None
    alert_preview: str | None = None


class ScanIssueResponse(BaseModel):
    symbol: str
    status: str
    detail: str


class ScanRunSummaryResponse(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None = None
    universe_name: str | None = None
    universe_version: str | None = None
    result_count: int
    symbols_scanned: int | None = None
    data_source: str | None = None


class ProductStatusResponse(BaseModel):
    data_source: str
    live_ready: bool
    claim: str
    last_candle_time: datetime | None = None
    symbols_with_candles: int
    environment: str
    plug_and_play: str


class MarketQuoteResponse(BaseModel):
    symbol: str
    current_price: Decimal | None = None
    current_price_change_percent: Decimal | None = None


class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    account_equity: Decimal = Field(gt=Decimal("0"))
    risk_percent: Decimal = Field(gt=Decimal("0"))
    slippage_per_share: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        description="Absolute per-share slippage applied against the trade (LONG: worse entry and exit).",
    )
    cost_per_trade: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        description="Flat round-trip transaction cost deducted once per completed trade.",
    )


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


class PerformanceMetricsResponse(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    total_pnl: Decimal
    average_pnl: Decimal
    total_r: Decimal
    average_r: Decimal
    maximum_drawdown: Decimal


class BacktestResponse(BaseModel):
    symbol: str
    timeframe: str
    completed_trades: int
    trades: list[BacktestTradeResponse]
    metrics: PerformanceMetricsResponse
