"""Map presented scan results to API response models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.api.schemas import (
    EligibleOpportunityResponse,
    FormingSetupResponse,
    OpportunityScanResponse,
    ScanIssueResponse,
    StrategyCandidateResponse,
    StrategyEvidenceResponse,
)
from app.application.alerts.composer import compose_scan_alert
from app.application.scan.scan_presentation import PresentedOpportunity, PresentedScan
from app.core.config import get_settings
from app.infrastructure.market_data.source import data_claim, normalize_market_data_source


def _candidate_response(candidate) -> StrategyCandidateResponse:
    return StrategyCandidateResponse(
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        direction=candidate.direction,
        entry_price=candidate.entry_price,
        stop_loss=candidate.stop_loss,
        target=candidate.target,
        risk_per_share=candidate.risk_per_share,
        reward=candidate.reward,
        risk_reward_ratio=candidate.risk_reward_ratio,
        setup_name=candidate.setup_name,
    )


def _evidence_response(evidence) -> StrategyEvidenceResponse:
    direction = getattr(evidence, "direction", "LONG")
    is_short = direction == "SHORT"
    return StrategyEvidenceResponse(
        resistance=evidence.resistance,
        breakout_candle_index=evidence.breakout_candle_index,
        breakout_candle_time=evidence.breakout_candle_time,
        retest_candle_index=evidence.retest_candle_index,
        retest_candle_time=evidence.retest_candle_time,
        confirmation_candle_index=evidence.confirmation_candle_index,
        confirmation_candle_time=evidence.confirmation_candle_time,
        atr_value=evidence.atr_value,
        volume_sma_value=evidence.volume_sma_value,
        breakout_volume=evidence.breakout_volume,
        retest_low=evidence.retest_low,
        confirmation_volume=evidence.confirmation_volume,
        decision=evidence.decision,
        direction=direction,
        structure_level=evidence.resistance,
        retest_extreme=evidence.retest_low,
        structure_label="support" if is_short else "resistance",
        retest_label="retest_high" if is_short else "retest_low",
    )


def _opportunity_response(item: PresentedOpportunity) -> EligibleOpportunityResponse:
    opp = item.opportunity
    return EligibleOpportunityResponse(
        symbol=opp.symbol,
        candidate=_candidate_response(opp.candidate),
        evidence=_evidence_response(opp.evidence),
        quality_score=item.quality.score,
        rank=item.rank,
        quantity=item.quantity,
        risk_amount=item.risk_amount,
        narrative=item.narrative,
        invalidation=item.invalidation,
        quality_reason=item.quality.reason,
        narrative_source=getattr(item, "narrative_source", "template"),
        invalidation_source=getattr(item, "invalidation_source", "template"),
        quality_critique=getattr(item, "quality_critique", None),
        quality_flags=list(getattr(item, "quality_flags", ()) or ()),
        volume_thrust=item.quality.volume_thrust,
        retest_tightness=item.quality.retest_tightness,
        risk_percent=item.quality.risk_percent,
        confirmation_volume_ratio=item.quality.confirmation_volume_ratio,
    )


def _forming_response(item) -> FormingSetupResponse:
    forming = item.forming
    direction = getattr(forming, "direction", "LONG")
    is_short = direction == "SHORT"
    return FormingSetupResponse(
        symbol=forming.symbol,
        timeframe=forming.timeframe,
        stage=forming.stage,
        resistance=forming.resistance,
        breakout_candle_index=forming.breakout_candle_index,
        breakout_candle_time=forming.breakout_candle_time,
        breakout_volume=forming.breakout_volume,
        atr_value=forming.atr_value,
        volume_sma_value=forming.volume_sma_value,
        bars_elapsed=forming.bars_elapsed,
        bars_remaining=forming.bars_remaining,
        reason=forming.reason,
        narrative=item.narrative,
        retest_candle_index=forming.retest_candle_index,
        retest_candle_time=forming.retest_candle_time,
        retest_low=forming.retest_low,
        direction=direction,
        structure_label="support" if is_short else "resistance",
        retest_label="retest_high" if is_short else "retest_low",
    )


def to_scan_response(
    *,
    presented: PresentedScan,
    universe_name: str,
    universe_version: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    scan_run_id: int | None,
    last_candle_time: datetime | None,
    data_quality_bullets: list[str] | None = None,
    ai_brief: str | None = None,
) -> OpportunityScanResponse:
    settings = get_settings()
    source = normalize_market_data_source(settings.market_data_source)
    claim = data_claim(settings)
    opportunities = [_opportunity_response(item) for item in presented.opportunities]
    top = [_opportunity_response(item) for item in presented.top]
    forming = [_forming_response(item) for item in presented.forming]
    issues = [
        ScanIssueResponse(symbol=item.symbol, status=item.status, detail=item.detail)
        for item in presented.report.issues
    ]
    alert = compose_scan_alert(
        presented,
        universe_name=universe_name,
        data_claim=claim,
        scan_run_id=scan_run_id,
        frontend_base_url=getattr(settings, "frontend_base_url", None),
        ai_brief=ai_brief,
        data_quality_bullets=data_quality_bullets,
    )
    return OpportunityScanResponse(
        universe_name=universe_name,
        universe_version=universe_version,
        timeframe=timeframe,
        start=start,
        end=end,
        symbols_scanned=presented.report.symbols_scanned,
        eligible_count=presented.report.eligible_count,
        no_setup_count=presented.report.no_setup_count,
        unavailable_count=presented.report.unavailable_count,
        error_count=presented.report.error_count,
        opportunities=opportunities,
        issues=issues,
        scan_run_id=scan_run_id,
        forming_count=presented.report.forming_count,
        forming=forming,
        top=top,
        data_source=source,
        data_claim=claim,
        last_candle_time=last_candle_time,
        alert_preview=alert.body,
        data_quality_bullets=data_quality_bullets,
        ai_brief=ai_brief,
        status="completed",
    )


async def enrich_current_prices_with_provider(response: OpportunityScanResponse, provider: Any) -> None:
    quote_fn = getattr(provider, "get_last_traded_prices", None) if provider is not None else None
    if quote_fn is None:
        return
    symbols = [item.symbol for item in response.opportunities]
    symbols.extend(item.symbol for item in response.forming)
    if not symbols:
        return
    try:
        quotes = await quote_fn(symbols)
    except Exception:
        return

    def apply_price(symbol: str, target) -> None:
        payload = quotes.get(symbol)
        if payload is None:
            return
        last_price = payload.get("last_price")
        target.current_price = Decimal(str(last_price)) if last_price is not None else None
        try:
            raw = payload.get("raw", {}) or {}
            net_change = raw.get("net_change")
            if net_change is not None and target.current_price is not None:
                net_change_decimal = Decimal(str(net_change))
                prev_close = target.current_price - net_change_decimal
                if prev_close != 0:
                    target.current_price_change_percent = (net_change_decimal / prev_close) * Decimal("100")
        except Exception:
            target.current_price_change_percent = None

    for item in response.opportunities:
        apply_price(item.symbol, item)
    for item in response.top:
        apply_price(item.symbol, item)
    for item in response.forming:
        apply_price(item.symbol, item)
