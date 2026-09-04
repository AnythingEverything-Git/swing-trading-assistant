"""Grounded Gemini Flash insights with hard guardrails against invented facts."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.narrative.gemini")

_PRICE_LIKE = re.compile(
    r"(?:₹|rs\.?\s*|inr\s*)?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?",
    re.IGNORECASE,
)
_MONEY_IN_TEXT = re.compile(
    r"(?P<prefix>₹|Rs\.?\s*|INR\s*)?(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+\.\d+|\d{4,})",
    re.IGNORECASE,
)

_MONEY_KEYS = frozenset(
    {
        "entry",
        "stop",
        "target",
        "high_52w",
        "low_52w",
        "last_close",
        "current_price",
        "resistance",
        "retest_low",
        "retest_high",
        "atr_value",
        "spot",
        "call_ltp",
        "put_ltp",
        "strike",
        "pivot",
        "resistance_1",
        "resistance_2",
        "resistance_3",
        "support_1",
        "support_2",
        "support_3",
        "risk_amount",
        "risk_per_share",
        "reward",
    }
)
_PCT_KEYS = frozenset({"change_percent", "current_price_change_percent", "pcr"})

_INSIGHT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "headline": {"type": "STRING"},
        "sections": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "label": {"type": "STRING"},
                    "text": {"type": "STRING"},
                },
                "required": ["label", "text"],
            },
        },
    },
    "required": ["title", "sections"],
}


@dataclass(frozen=True)
class InsightSection:
    label: str
    text: str


@dataclass(frozen=True)
class InsightResult:
    title: str
    bullets: tuple[str, ...]
    provider: str
    grounded: bool
    detail: str | None = None
    headline: str | None = None
    sections: tuple[InsightSection, ...] = ()


def format_money_2dp(value: Any) -> str | None:
    """Format a numeric money-like value to exactly two decimal places."""
    if value is None or value == "":
        return None
    try:
        quantized = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    return f"{quantized:.2f}"


def format_pct_2dp(value: Any) -> str | None:
    return format_money_2dp(value)


def normalize_insight_context(context: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy context with money/percent fields forced to 2 decimal strings."""

    def walk(node: Any, parent_key: str | None = None) -> Any:
        if isinstance(node, dict):
            return {str(k): walk(v, str(k)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(item, parent_key) for item in node]
        key = (parent_key or "").lower()
        if key in _MONEY_KEYS or key.endswith("_price") or key.endswith("_ltp"):
            formatted = format_money_2dp(node)
            return formatted if formatted is not None else node
        if key in _PCT_KEYS or key.endswith("_percent"):
            formatted = format_pct_2dp(node)
            return formatted if formatted is not None else node
        return node

    return walk(context)  # type: ignore[return-value]


def format_currency_tokens_in_text(text: str) -> str:
    """Rewrite decimal/currency tokens in free text to two decimal places."""

    def repl(match: re.Match[str]) -> str:
        prefix = match.group("prefix") or ""
        raw = match.group("num").replace(",", "")
        if "." not in raw and len(raw) <= 3:
            return match.group(0)
        formatted = format_money_2dp(raw)
        if formatted is None:
            return match.group(0)
        if prefix:
            return f"{prefix.strip()} {formatted}".replace("  ", " ")
        if "." in raw or Decimal(raw) >= 100:
            return f"₹{formatted}"
        return formatted

    return _MONEY_IN_TEXT.sub(repl, text)


def _facts_blob(context: dict[str, Any]) -> str:
    return json.dumps(context, default=str, ensure_ascii=True)


def _extract_numeric_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _PRICE_LIKE.finditer(text):
        raw = match.group(0)
        cleaned = re.sub(r"(?i)^(₹|rs\.?\s*|inr\s*)", "", raw).replace(",", "").strip().lower()
        if not cleaned:
            continue
        tokens.add(cleaned)
        money = format_money_2dp(cleaned)
        if money:
            tokens.add(money)
            tokens.add(money.rstrip("0").rstrip(".") if "." in money else money)
    return tokens


def validate_grounded_bullets(bullets: list[str], context: dict[str, Any]) -> list[str]:
    """Drop bullets that introduce numeric tokens not present in the grounded context."""
    allowed = _extract_numeric_tokens(_facts_blob(context))
    safe: list[str] = []
    for bullet in bullets:
        cleaned = bullet.strip().lstrip("-• ").strip()
        if not cleaned:
            continue
        formatted = format_currency_tokens_in_text(cleaned)
        novel = _extract_numeric_tokens(formatted) - allowed
        novel = {token for token in novel if not re.fullmatch(r"\d", token)}
        if novel:
            logger.info("gemini.guardrail_drop novel_tokens=%s bullet=%s", sorted(novel), formatted)
            continue
        safe.append(formatted)
    return safe[:6]


def _sections_to_bullets(sections: list[InsightSection]) -> tuple[str, ...]:
    return tuple(f"{item.label}: {item.text}" if item.label else item.text for item in sections)


def template_insight(tab: str, context: dict[str, Any]) -> InsightResult:
    symbol = str(context.get("symbol") or "Symbol")
    if tab == "technical":
        indicators = context.get("indicators") or []
        sections: list[InsightSection] = []
        for item in indicators[:4]:
            if isinstance(item, dict):
                name = str(item.get("name") or "Indicator")
                signal = str(item.get("signal") or "n/a")
                value = item.get("value")
                value_txt = format_money_2dp(value) if value is not None else None
                text = f"{signal}" + (f" · {value_txt}" if value_txt else "")
                sections.append(InsightSection(label=name, text=text))
        if not sections:
            sections = [InsightSection(label="Technicals", text="Insufficient candle history for technical signals.")]
        return InsightResult(
            title=f"{symbol} technical snapshot",
            headline="Technical analysis from indicator readings on persisted candles.",
            bullets=_sections_to_bullets(sections),
            sections=tuple(sections),
            provider="template",
            grounded=True,
        )
    if tab == "news":
        sections = []
        for item in (context.get("announcements") or [])[:3]:
            if isinstance(item, dict) and item.get("title"):
                sections.append(InsightSection(label="Announcement", text=str(item["title"])))
        for item in (context.get("events") or [])[:2]:
            if isinstance(item, dict) and item.get("title"):
                sections.append(InsightSection(label="Event", text=str(item["title"])))
        if not sections:
            sections = [
                InsightSection(
                    label="News",
                    text="No recent NSE announcements/events were returned for this symbol.",
                )
            ]
        return InsightResult(
            title=f"{symbol} news & events",
            headline="Headlines grounded in the loaded feed only.",
            bullets=_sections_to_bullets(sections),
            sections=tuple(sections),
            provider="template",
            grounded=True,
        )
    if tab == "setup":
        setup = context.get("setup") if isinstance(context.get("setup"), dict) else context
        sections = []
        if isinstance(setup, dict):
            if setup.get("narrative"):
                sections.append(InsightSection(label="Thesis", text=str(setup["narrative"])))
            for label, key in (
                ("Buy/sell at", "entry"),
                ("Safety exit", "stop"),
                ("Profit goal", "target"),
            ):
                money = format_money_2dp(setup.get(key))
                if money:
                    sections.append(InsightSection(label=label, text=f"₹{money}"))
            if setup.get("stage"):
                sections.append(InsightSection(label="Stage", text=str(setup["stage"])))
        if not sections:
            sections = [InsightSection(label="Setup", text="No confirmed trade plan for this symbol yet.")]
        return InsightResult(
            title=f"{symbol} setup summary",
            headline="How this swing setup was derived from scan evidence — not broker advice.",
            bullets=_sections_to_bullets(sections),
            sections=tuple(sections),
            provider="template",
            grounded=True,
        )

    performance = context.get("performance") or []
    sections = []
    # Prefer 1Y first for overview AI narrative
    ordered_perf = sorted(
        [item for item in performance if isinstance(item, dict)],
        key=lambda item: 0 if str(item.get("label") or "") == "1Y" else 1,
    )
    for item in ordered_perf:
        if item.get("change_percent") is not None:
            pct = format_pct_2dp(item.get("change_percent"))
            label = str(item.get("label") or "Return")
            sections.append(InsightSection(label=label, text=f"{pct}%" if pct is not None else "n/a"))
    for key, label in (("high_52w", "52W high"), ("low_52w", "52W low"), ("last_close", "Last close")):
        money = format_money_2dp(context.get(key))
        if money:
            sections.append(InsightSection(label=label, text=f"₹{money}"))
    setup = context.get("setup")
    if isinstance(setup, dict):
        if setup.get("narrative"):
            sections.append(InsightSection(label="Setup", text=str(setup["narrative"])))
        for label, key in (("Entry", "entry"), ("Stop", "stop"), ("Target", "target")):
            money = format_money_2dp(setup.get(key))
            if money:
                sections.append(InsightSection(label=label, text=f"₹{money}"))
    if not sections:
        sections = [
            InsightSection(label="Overview", text="Overview uses persisted candles and scan evidence only.")
        ]
    return InsightResult(
        title=f"{symbol} overview & setup",
        headline="1-year performance and setup levels from loaded facts only.",
        bullets=_sections_to_bullets(sections[:6]),
        sections=tuple(sections[:6]),
        provider="template",
        grounded=True,
    )


def _parse_structured(parsed: dict[str, Any], fallback: InsightResult) -> tuple[str, str | None, list[InsightSection]]:
    title = str(parsed.get("title") or fallback.title).strip()
    headline_raw = parsed.get("headline")
    headline = str(headline_raw).strip() if headline_raw else fallback.headline

    sections: list[InsightSection] = []
    raw_sections = parsed.get("sections")
    if isinstance(raw_sections, list):
        for item in raw_sections:
            if isinstance(item, dict):
                label = str(item.get("label") or "").strip()
                text = str(item.get("text") or "").strip()
                if text:
                    sections.append(
                        InsightSection(
                            label=label or "Note",
                            text=format_currency_tokens_in_text(text),
                        )
                    )
            elif item:
                sections.append(InsightSection(label="Note", text=format_currency_tokens_in_text(str(item))))

    if not sections:
        raw_bullets = parsed.get("bullets") or []
        if isinstance(raw_bullets, list):
            for bullet in raw_bullets:
                if isinstance(bullet, dict):
                    label = str(bullet.get("label") or "Note").strip()
                    text = str(bullet.get("text") or bullet.get("body") or "").strip()
                    if text:
                        sections.append(
                            InsightSection(label=label, text=format_currency_tokens_in_text(text))
                        )
                else:
                    text = str(bullet).strip()
                    if text:
                        if ":" in text:
                            label, rest = text.split(":", 1)
                            sections.append(
                                InsightSection(
                                    label=label.strip() or "Note",
                                    text=format_currency_tokens_in_text(rest.strip()),
                                )
                            )
                        else:
                            sections.append(
                                InsightSection(label="Note", text=format_currency_tokens_in_text(text))
                            )
    return title, headline, sections


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
        normalized = normalize_insight_context(context)
        fallback = template_insight(tab, normalized)
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
            "All INR prices MUST use exactly two decimal places (example 1520.50). "
            "Return strict JSON with keys title, headline, sections. "
            "sections is an array of {label, text} objects (max 5). "
            "Keep labels short (Performance, Setup, Entry, Risk)."
        )
        if tab == "overview":
            focus = (
                "Focus on the stock's performance over the last 1 year (1Y), "
                "and briefly relate shorter windows (1D/1W/1M/3M) and 52-week range. "
                "Be brief but informative. Fact-based analysis only."
            )
        elif tab == "setup":
            focus = (
                "Explain the swing strategy and how this setup was derived from the evidence "
                "(breakout/breakdown, retest, confirmation, ATR, volumes, levels). "
                "Be brief but informative. Fact-based analysis only. Do not invent levels."
            )
        elif tab == "technical":
            focus = (
                "Provide a brief technical analysis snapshot from the indicator readings and pivots only. "
                "Mention trend (SMAs/EMAs), momentum (RSI/MACD), and volatility/volume when present. "
                "Fact-based analysis only."
            )
        else:
            focus = "Write a concise trader-facing structured summary from these facts only."
        user = (
            f"Tab={tab}\n"
            f"{focus}\n"
            f"Facts JSON:\n{_facts_blob(normalized)}\n"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": _INSIGHT_RESPONSE_SCHEMA,
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
                    headline=fallback.headline,
                    bullets=fallback.bullets,
                    sections=fallback.sections,
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
            if not isinstance(parsed, dict):
                parsed = {}
            title, headline, sections = _parse_structured(parsed, fallback)
            grounded_texts = validate_grounded_bullets(
                [f"{s.label}: {s.text}" for s in sections],
                normalized,
            )
            if not grounded_texts:
                return InsightResult(
                    title=fallback.title,
                    headline=fallback.headline,
                    bullets=fallback.bullets,
                    sections=fallback.sections,
                    provider="template",
                    grounded=True,
                    detail="gemini_ungrounded_or_empty",
                )
            safe_sections: list[InsightSection] = []
            for line in grounded_texts:
                if ": " in line:
                    label, rest = line.split(": ", 1)
                    safe_sections.append(InsightSection(label=label, text=rest))
                else:
                    safe_sections.append(InsightSection(label="Note", text=line))
            return InsightResult(
                title=title,
                headline=headline,
                bullets=tuple(grounded_texts),
                sections=tuple(safe_sections),
                provider="gemini",
                grounded=True,
            )
        except Exception as exc:
            logger.warning("gemini.insight_failed: %s", exc)
            return InsightResult(
                title=fallback.title,
                headline=fallback.headline,
                bullets=fallback.bullets,
                sections=fallback.sections,
                provider="template",
                grounded=True,
                detail=str(exc),
            )


__all__ = [
    "GeminiNarrator",
    "InsightResult",
    "InsightSection",
    "template_insight",
    "validate_grounded_bullets",
    "normalize_insight_context",
    "format_money_2dp",
    "format_currency_tokens_in_text",
]
