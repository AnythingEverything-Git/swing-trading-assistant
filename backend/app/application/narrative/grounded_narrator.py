"""Thin facade over Gemini + template fallback for grounded rephrase tasks.

Strategy owns Entry / SL / Target. This module only rewrites wording from
explicit facts and rejects responses that introduce novel numeric tokens.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.application.narrative.gemini_narrator import (
    _extract_numeric_tokens,
    format_currency_tokens_in_text,
)
from app.core.config import Settings, get_settings

logger = logging.getLogger("app.narrative.grounded")


@dataclass(frozen=True)
class GroundedTextResult:
    text: str
    provider: str
    grounded: bool
    detail: str | None = None


@dataclass(frozen=True)
class GroundedBulletsResult:
    bullets: tuple[str, ...]
    provider: str
    grounded: bool
    detail: str | None = None


def narrative_llm_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    provider = (cfg.narrative_provider or "template").strip().lower()
    key = (cfg.google_api_key or "").strip()
    return provider == "llm" and bool(key)


def _facts_blob(facts: dict[str, Any]) -> str:
    return json.dumps(facts, default=str, ensure_ascii=True, sort_keys=True)


def _text_is_grounded(text: str, allowed: set[str]) -> bool:
    formatted = format_currency_tokens_in_text(text.strip())
    novel = _extract_numeric_tokens(formatted) - allowed
    novel = {token for token in novel if not re.fullmatch(r"\d", token)}
    return not novel


def validate_grounded_text(text: str, facts: dict[str, Any]) -> str | None:
    cleaned = format_currency_tokens_in_text((text or "").strip())
    if not cleaned:
        return None
    allowed = _extract_numeric_tokens(_facts_blob(facts))
    if not _text_is_grounded(cleaned, allowed):
        logger.info("grounded.guardrail_drop text=%s", cleaned[:160])
        return None
    return cleaned


def validate_grounded_bullets(bullets: list[str], facts: dict[str, Any]) -> list[str]:
    safe: list[str] = []
    for bullet in bullets:
        cleaned = validate_grounded_text(str(bullet).lstrip("-• ").strip(), facts)
        if cleaned:
            safe.append(cleaned)
    return safe


class GroundedNarrator:
    """Shared Gemini call site for scan polish, critic, briefs, and interpreters."""

    def __init__(self, http_client: Any, settings: Settings | None = None) -> None:
        self._client = http_client
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return narrative_llm_enabled(self._settings)

    async def _generate_json(
        self,
        *,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
        timeout: float = 25.0,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        key = (self._settings.google_api_key or "").strip()
        model = (self._settings.gemini_model or "gemini-2.0-flash").strip()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }
        try:
            resp = await self._client.post(url, json=payload, timeout=timeout)
            status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
            if status is None or int(status) >= 400:
                logger.warning("grounded.gemini_http status=%s", status)
                return None
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
            return parsed if isinstance(parsed, dict) else None
        except Exception as exc:
            logger.warning("grounded.gemini_failed: %s", exc)
            return None

    async def rephrase_text(
        self,
        *,
        kind: str,
        source_text: str,
        facts: dict[str, Any],
        instruction: str,
    ) -> GroundedTextResult:
        _ = kind
        source = (source_text or "").strip()
        if not source:
            return GroundedTextResult(text="", provider="template", grounded=True, detail="empty")

        facts_with_source = {**facts, "source_text": source}
        if not self.enabled:
            return GroundedTextResult(
                text=source, provider="template", grounded=True, detail="llm_disabled"
            )

        schema = {
            "type": "OBJECT",
            "properties": {"text": {"type": "STRING"}},
            "required": ["text"],
        }
        system = (
            "You are TradePilot. Rephrase the source text for a swing trader. "
            "STRICT: use ONLY the JSON facts and source_text. "
            "Do not invent Entry, Stop, Target, prices, dates, ratios, or advice. "
            "Do not change any number. Keep INR amounts to two decimals when present. "
            f"{instruction} "
            "Return JSON {text}."
        )
        user = f"Facts JSON:\n{_facts_blob(facts_with_source)}\n"
        parsed = await self._generate_json(system=system, user=user, response_schema=schema)
        if not parsed:
            return GroundedTextResult(
                text=source, provider="template", grounded=True, detail="gemini_failed"
            )
        candidate = str(parsed.get("text") or "").strip()
        safe = validate_grounded_text(candidate, facts_with_source)
        if not safe:
            return GroundedTextResult(
                text=source, provider="template", grounded=True, detail="gemini_ungrounded"
            )
        if safe == source:
            return GroundedTextResult(
                text=source, provider="template", grounded=True, detail="unchanged"
            )
        return GroundedTextResult(text=safe, provider="llm", grounded=True)

    async def generate_bullets(
        self,
        *,
        kind: str,
        facts: dict[str, Any],
        instruction: str,
        fallback: list[str],
        max_bullets: int = 6,
    ) -> GroundedBulletsResult:
        _ = kind
        if not self.enabled:
            return GroundedBulletsResult(
                bullets=tuple(fallback[:max_bullets]),
                provider="template",
                grounded=True,
                detail="llm_disabled",
            )
        schema = {
            "type": "OBJECT",
            "properties": {
                "bullets": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["bullets"],
        }
        system = (
            "You are TradePilot. Write short beginner-friendly bullets from the JSON facts only. "
            "STRICT: do not invent prices, Entry, Stop, Target, or unstated metrics. "
            f"{instruction} "
            f"Return JSON {{bullets}} with at most {max_bullets} strings."
        )
        user = f"Facts JSON:\n{_facts_blob(facts)}\n"
        parsed = await self._generate_json(system=system, user=user, response_schema=schema)
        if not parsed:
            return GroundedBulletsResult(
                bullets=tuple(fallback[:max_bullets]),
                provider="template",
                grounded=True,
                detail="gemini_failed",
            )
        raw = parsed.get("bullets") or []
        if not isinstance(raw, list):
            return GroundedBulletsResult(
                bullets=tuple(fallback[:max_bullets]),
                provider="template",
                grounded=True,
                detail="bad_shape",
            )
        safe = validate_grounded_bullets([str(b) for b in raw], facts)[:max_bullets]
        if not safe:
            return GroundedBulletsResult(
                bullets=tuple(fallback[:max_bullets]),
                provider="template",
                grounded=True,
                detail="ungrounded",
            )
        return GroundedBulletsResult(bullets=tuple(safe), provider="llm", grounded=True)


__all__ = [
    "GroundedBulletsResult",
    "GroundedNarrator",
    "GroundedTextResult",
    "narrative_llm_enabled",
    "validate_grounded_bullets",
    "validate_grounded_text",
]
