"""Explain scan data-quality issues for beginners. Numbers stay in issues[]."""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.application.narrative.grounded_narrator import GroundedBulletsResult, GroundedNarrator

# Keep the scan desk calm: tiny UNAVAILABLE gaps are normal, not an outage.
_TRIVIAL_UNAVAILABLE_MAX = 5


def issue_severity(issues: list[dict[str, Any]]) -> str:
    """Return 'none' | 'low' | 'high' for UI emphasis."""
    if not issues:
        return "none"
    counts: dict[str, int] = {}
    for item in issues:
        status = str(item.get("status") or "UNKNOWN").upper()
        counts[status] = counts.get(status, 0) + 1
    if counts.get("ERROR", 0) > 0:
        return "high"
    unavailable = counts.get("UNAVAILABLE", 0)
    if unavailable > _TRIVIAL_UNAVAILABLE_MAX:
        return "high"
    if unavailable > 0 or sum(counts.values()) > 0:
        return "low"
    return "none"


def _friendly_detail(detail: str) -> str:
    text = (detail or "").strip()
    lowered = text.lower()
    if "at least one" in lowered or "empty" in lowered or "no candle" in lowered:
        return "No usable daily candles in the scan window."
    if "not found" in lowered or "missing" in lowered:
        return "Candle history missing for this symbol."
    return text


def _template_bullets(issues: list[dict[str, Any]], counts: dict[str, int], *, severity: str) -> list[str]:
    if severity == "low":
        unavailable = counts.get("UNAVAILABLE", 0)
        symbols = [str(i.get("symbol") or "") for i in issues if i.get("symbol")]
        sample = ", ".join(symbols[:3])
        if unavailable == 1 and sample:
            return [f"{sample} had no usable candles in this window (skipped — not a failed setup)."]
        if unavailable and sample:
            return [
                f"{unavailable} symbols lacked candles (e.g. {sample}). "
                "They were skipped; Ready now / Almost ready are unaffected."
            ]
        return ["A few symbols lacked candles and were skipped."]

    bullets: list[str] = [
        "UNAVAILABLE means candles were missing for that symbol — it is not the same as 'no setup'.",
    ]
    if counts.get("ERROR"):
        bullets.append(
            f"{counts['ERROR']} symbol(s) hit an evaluator ERROR — refresh data and re-scan if this clusters."
        )
    if counts.get("UNAVAILABLE"):
        bullets.append(f"{counts['UNAVAILABLE']} symbol(s) marked UNAVAILABLE in this scan.")
    symbols = [str(i.get("symbol") or "") for i in issues if i.get("symbol")]
    if symbols:
        top = Counter(symbols).most_common(3)
        cluster = ", ".join(f"{sym} ({n})" for sym, n in top if sym)
        if cluster:
            bullets.append(f"Most affected: {cluster}.")
    bullets.append("Refresh market data, then re-run the scan if issues stay elevated.")
    return bullets[:6]


async def explain_data_issues(
    narrator: GroundedNarrator | None,
    *,
    issues: list[dict[str, Any]],
) -> GroundedBulletsResult:
    counts: dict[str, int] = {}
    for item in issues:
        status = str(item.get("status") or "UNKNOWN").upper()
        counts[status] = counts.get(status, 0) + 1
    severity = issue_severity(issues)
    if severity == "none":
        return GroundedBulletsResult(bullets=(), provider="template", grounded=True, detail="none")

    fallback = _template_bullets(issues, counts, severity=severity)
    # Low severity: keep one short line; skip LLM so the desk stays calm.
    if severity == "low" or narrator is None or not narrator.enabled:
        return GroundedBulletsResult(
            bullets=tuple(fallback),
            provider="template",
            grounded=True,
            detail=severity,
        )

    facts = {
        "issue_count": len(issues),
        "counts": counts,
        "severity": severity,
        "sample": [
            {
                "symbol": i.get("symbol"),
                "status": i.get("status"),
                "detail": _friendly_detail(str(i.get("detail") or "")),
            }
            for i in issues[:12]
        ],
        "notes": [
            "UNAVAILABLE is not no-setup",
            "ERROR needs data refresh or retry",
        ],
    }
    return await narrator.generate_bullets(
        kind="data_quality",
        facts=facts,
        instruction=(
            "Explain material data issues briefly for a beginner. "
            "Emphasize UNAVAILABLE is not no setup. Do not alarm for tiny gaps."
        ),
        fallback=fallback,
        max_bullets=5,
    )


__all__ = ["explain_data_issues", "issue_severity", "_friendly_detail"]
