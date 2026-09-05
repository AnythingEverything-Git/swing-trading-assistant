"""Similar-setup fingerprints + forward N-bar outcomes from candles (not live P&L)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence

from app.application.narrative.grounded_narrator import GroundedNarrator, GroundedTextResult
from app.domain.market_data import Candle


@dataclass(frozen=True)
class SetupFingerprint:
    symbol: str
    direction: str
    confirmation_time: datetime
    quality_score: Decimal
    volume_thrust: Decimal
    retest_tightness: Decimal
    risk_percent: Decimal
    atr_percent: Decimal
    risk_reward_ratio: Decimal
    scan_run_id: int | None = None
    entry: Decimal | None = None
    stop: Decimal | None = None
    target: Decimal | None = None


@dataclass(frozen=True)
class SimilarSetupMatch:
    fingerprint: SetupFingerprint
    distance: Decimal
    forward_bars: int
    forward_return_pct: Decimal | None
    hit_target: bool | None
    hit_stop: bool | None
    blurb: str | None
    blurb_provider: str


def fingerprint_from_opportunity_payload(
    item: dict[str, Any],
    *,
    scan_run_id: int | None = None,
) -> SetupFingerprint | None:
    try:
        candidate = item.get("candidate") or {}
        evidence = item.get("evidence") or {}
        symbol = str(item.get("symbol") or candidate.get("symbol") or "").upper()
        if not symbol:
            return None
        entry = Decimal(str(candidate["entry_price"]))
        atr = Decimal(str(evidence.get("atr_value") or "0"))
        atr_pct = (atr / entry * Decimal("100")) if entry else Decimal("0")
        conf_raw = evidence.get("confirmation_candle_time")
        if isinstance(conf_raw, datetime):
            conf_time = conf_raw
        else:
            conf_time = datetime.fromisoformat(str(conf_raw).replace("Z", "+00:00"))
        quality = item.get("quality_score")
        volume_thrust = Decimal(str(item.get("volume_thrust") or "1"))
        retest_tightness = Decimal(str(item.get("retest_tightness") or "1"))
        risk_percent = Decimal(str(item.get("risk_percent") or "0"))
        return SetupFingerprint(
            symbol=symbol,
            direction=str(candidate.get("direction") or "LONG").upper(),
            confirmation_time=conf_time,
            quality_score=Decimal(str(quality or "0")),
            volume_thrust=volume_thrust,
            retest_tightness=retest_tightness,
            risk_percent=risk_percent,
            atr_percent=atr_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            risk_reward_ratio=Decimal(str(candidate.get("risk_reward_ratio") or "0")),
            scan_run_id=scan_run_id,
            entry=entry,
            stop=Decimal(str(candidate.get("stop_loss"))),
            target=Decimal(str(candidate.get("target"))),
        )
    except Exception:
        return None


def fingerprint_distance(a: SetupFingerprint, b: SetupFingerprint) -> Decimal:
    if a.direction != b.direction:
        return Decimal("999")
    score_d = abs(a.quality_score - b.quality_score) / Decimal("100")
    atr_d = abs(a.atr_percent - b.atr_percent) / Decimal("10")
    rr_d = abs(a.risk_reward_ratio - b.risk_reward_ratio) / Decimal("3")
    risk_d = abs(a.risk_percent - b.risk_percent) / Decimal("5")
    return (score_d + atr_d + rr_d + risk_d).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def forward_outcome_from_candles(
    candles: Sequence[Candle],
    *,
    confirmation_time: datetime,
    direction: str,
    entry: Decimal | None,
    stop: Decimal | None,
    target: Decimal | None,
    forward_bars: int = 10,
) -> tuple[Decimal | None, bool | None, bool | None]:
    if not candles or entry is None:
        return None, None, None
    idx = None
    for i, candle in enumerate(candles):
        if candle.timestamp >= confirmation_time:
            idx = i
            break
    if idx is None:
        return None, None, None
    end = min(len(candles) - 1, idx + max(1, forward_bars))
    if end <= idx:
        return None, None, None
    start_close = candles[idx].close
    end_close = candles[end].close
    if start_close == 0:
        return None, None, None
    if direction == "SHORT":
        ret = ((start_close - end_close) / start_close * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        ret = ((end_close - start_close) / start_close * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    hit_target = None
    hit_stop = None
    if stop is not None and target is not None:
        hit_target = False
        hit_stop = False
        for candle in candles[idx + 1 : end + 1]:
            if direction == "SHORT":
                if candle.low <= target:
                    hit_target = True
                    break
                if candle.high >= stop:
                    hit_stop = True
                    break
            else:
                if candle.high >= target:
                    hit_target = True
                    break
                if candle.low <= stop:
                    hit_stop = True
                    break
    return ret, hit_target, hit_stop


def dedupe_fingerprints(corpus: Sequence[SetupFingerprint]) -> list[SetupFingerprint]:
    """Keep one fingerprint per symbol + direction + confirmation day (latest scan wins)."""
    best: dict[tuple[str, str, str], SetupFingerprint] = {}
    for item in corpus:
        key = (item.symbol, item.direction, item.confirmation_time.date().isoformat())
        prev = best.get(key)
        if prev is None:
            best[key] = item
            continue
        prev_run = prev.scan_run_id or 0
        cur_run = item.scan_run_id or 0
        if cur_run >= prev_run:
            best[key] = item
    return list(best.values())


def rank_similar(
    query: SetupFingerprint,
    corpus: Sequence[SetupFingerprint],
    *,
    limit: int = 5,
    exclude_query_symbol: bool = True,
) -> list[tuple[SetupFingerprint, Decimal]]:
    """Nearest neighbors by fingerprint distance; one row per peer symbol."""
    scored: list[tuple[SetupFingerprint, Decimal]] = []
    for item in dedupe_fingerprints(corpus):
        if exclude_query_symbol and item.symbol == query.symbol:
            continue
        dist = fingerprint_distance(query, item)
        if dist >= Decimal("999"):
            continue
        scored.append((item, dist))
    scored.sort(key=lambda pair: (pair[1], pair[0].symbol, pair[0].confirmation_time))

    # Prefer diverse symbols (first occurrence is nearest for that symbol).
    out: list[tuple[SetupFingerprint, Decimal]] = []
    seen_symbols: set[str] = set()
    for item, dist in scored:
        if item.symbol in seen_symbols:
            continue
        seen_symbols.add(item.symbol)
        out.append((item, dist))
        if len(out) >= max(0, limit):
            break
    return out


async def similar_blurb(
    narrator: GroundedNarrator | None,
    *,
    match: SetupFingerprint,
    forward_return_pct: Decimal | None,
    forward_bars: int,
) -> GroundedTextResult:
    if forward_return_pct is None:
        fallback = (
            f"Next {forward_bars} sessions: not enough candle history to measure "
            f"(path from confirmation, not live P&L)."
        )
        ret = "unavailable"
    else:
        ret = str(forward_return_pct)
        fallback = (
            f"Next {forward_bars} sessions averaged {ret}% "
            f"(candle path from confirmation, not live P&L)."
        )
    facts = {
        "peer_symbol": match.symbol,
        "peer_date": match.confirmation_time.date().isoformat(),
        "direction": match.direction,
        "forward_bars": forward_bars,
        "forward_return_pct": ret,
        "quality_score": str(match.quality_score),
        "atr_percent": str(match.atr_percent),
        "risk_reward_ratio": str(match.risk_reward_ratio),
    }
    if narrator is None or not narrator.enabled:
        return GroundedTextResult(text=fallback, provider="template", grounded=True)
    return await narrator.rephrase_text(
        kind="similar_setup",
        source_text=fallback,
        facts=facts,
        instruction="One sentence comparing this peer setup and its measured forward path.",
    )


__all__ = [
    "SetupFingerprint",
    "SimilarSetupMatch",
    "fingerprint_from_opportunity_payload",
    "fingerprint_distance",
    "forward_outcome_from_candles",
    "dedupe_fingerprints",
    "rank_similar",
    "similar_blurb",
]
