"""Grounded Gemini Flash insights with hard guardrails against invented facts."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.narrative.gemini")

_PRICE_LIKE = re.compile(
    r"(?:₹|rs\.?\s*|inr\s*)?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InsightResult:
    title: str
    bullets: tuple[str, ...]
    provider: str
    grounded: bool
    detail: str | None = None


def _facts_blob(context: dict[str, Any]) -> str:
    return json.dumps(context, default=str, ensure_ascii=True)


def _extract_numeric_tokens(text: str) -> set[str]:
    return {m.group(0).replace(",", "").lower() for m in _PRICE_LIKE.finditer(text)}


def validate_grounded_bullets(bullets: list[str], context: dict[str, Any]) -> list[str]:
    """Drop bullets that introduce numeric tokens not present in the grounded context."""
    allowed = _extract_numeric_tokens(_facts_blob(context))
    # Allow common non-price percentages already in context; still block novel numbers.
    safe: list[str] = []
    for bullet in bullets:
        cleaned = bullet.strip().lstrip("-• ").strip()
        if not cleaned:
            continue
        novel = _extract_numeric_tokens(cleaned) - allowed
        # Ignore very small tokens that are ordinals/years already unlikely; still strict.
        novel = {token for token in novel if not re.fullmatch(r"\d", token)}
        if novel:
            logger.info("gemini.guardrail_drop novel_tokens=%s bullet=%s", sorted(novel), cleaned)
            continue
        safe.append(cleaned)
    return safe[:6]


def template_insight(tab: str, context: dict[str, Any]) -> InsightResult:
    symbol = str(context.get("symbol") or "Symbol")
    if tab == "technical":
        indicators = context.get("indicators") or []
        labels = []
        for item in indicators[:4]:
            if isinstance(item, dict):
                labels.append(f"{item.get('name')}: {item.get('signal')}")
        bullets = labels or ["Insufficient candle history for technical signals."]
        return InsightResult(
            title=f"{symbol} technical snapshot",
            bullets=tuple(bullets),
            provider="template",
            grounded=True,
        )
    if tab == "news":
        headlines = []
        for item in (context.get("announcements") or [])[:3]:
            if isinstance(item, dict) and item.get("title"):
                headlines.append(str(item["title"]))
        for item in (context.get("events") or [])[:2]:
            if isinstance(item, dict) and item.get("title"):
                headlines.append(str(item["title"]))
        if not headlines:
            headlines = ["No recent NSE announcements/events were returned for this symbol."]
        return InsightResult(
            title=f"{symbol} news & events",
            bullets=tuple(headlines),
            provider="template",
            grounded=True,
        )

    performance = context.get("performance") or []
    bullets = []
    for item in performance:
        if isinstance(item, dict) and item.get("change_percent") is not None:
            bullets.append(f"{item.get('label')}: {item.get('change_percent')}%")
    setup = context.get("setup")
    if isinstance(setup, dict) and setup.get("narrative"):
        bullets.append(str(setup["narrative"]))
    if not bullets:
        bullets = ["Overview uses persisted candles and scan evidence only."]
    return InsightResult(
        title=f"{symbol} overview",
        bullets=tuple(bullets[:6]),
        provider="template",
        grounded=True,
    )


class GeminiNarrator:
    def __init__(self, http_client: Any, settings: Settings | None = None) -> None:
        self._client = http_client
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        provider = (self._settings.narrative_provider or "template").strip().lower()
        key = (self._settings.google_api_key or "").strip()
        return provider == "llm" and bool(key)

    async def generate_insight(self, *, tab: str, context: dict[str, Any]) -> InsightResult:
        fallback = template_insight(tab, context)
        if not self.enabled:
            return fallback

        key = (self._settings.google_api_key or "").strip()
        model = (self._settings.gemini_model or "gemini-2.0-flash").strip()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        system = (
            "You are TradePilot research assistant. Use ONLY the JSON facts provided. "
            "Do not invent prices, Entry, Stop Loss, Target, OI, IV, news headlines, or dates. "
            "If a fact is missing, say it is unavailable. "
            "Return strict JSON: {\"title\": string, \"bullets\": string[]} with at most 5 bullets."
        )
        user = (
            f"Tab={tab}\n"
            f"Facts JSON:\n{_facts_blob(context)}\n"
            "Write a concise trader-facing summary from these facts only."
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        try:
            resp = await self._client.post(url, json=payload, timeout=20.0)
            status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
            if status is None or int(status) >= 400:
                body_snip = ""
                try:
                    body_snip = str(resp.text)[:180]
                except Exception:
                    body_snip = ""
                return InsightResult(
                    title=fallback.title,
                    bullets=fallback.bullets,
                    provider="template",
                    grounded=True,
                    detail=f"gemini_http_{status} model={model} {body_snip}",
                )
            body = resp.json()
            if hasattr(body, "__await__"):
                body = await body
            text = (
                body.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            parsed = json.loads(text) if text else {}
            title = str(parsed.get("title") or fallback.title).strip()
            raw_bullets = parsed.get("bullets") or []
            if not isinstance(raw_bullets, list):
                raw_bullets = []
            bullets = validate_grounded_bullets([str(b) for b in raw_bullets], context)
            if not bullets:
                return InsightResult(
                    title=fallback.title,
                    bullets=fallback.bullets,
                    provider="template",
                    grounded=True,
                    detail="gemini_ungrounded_or_empty",
                )
            return InsightResult(
                title=title,
                bullets=tuple(bullets),
                provider="gemini",
                grounded=True,
            )
        except Exception as exc:
            logger.warning("gemini.insight_failed: %s", exc)
            return InsightResult(
                title=fallback.title,
                bullets=fallback.bullets,
                provider="template",
                grounded=True,
                detail=str(exc),
            )


__all__ = [
    "GeminiNarrator",
    "InsightResult",
    "template_insight",
    "validate_grounded_bullets",
]
