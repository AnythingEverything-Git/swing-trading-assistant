"""Rephrase plan-deduction steps with Gemini — wording only, no new facts."""
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

logger = logging.getLogger("app.narrative.deduction_rephrase")

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "details": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                },
                "required": ["id", "summary", "details"],
            },
        }
    },
    "required": ["steps"],
}


@dataclass(frozen=True)
class DeductionStep:
    id: str
    title: str
    value: str
    summary: str
    details: tuple[str, ...]


@dataclass(frozen=True)
class DeductionRephraseResult:
    steps: tuple[DeductionStep, ...]
    provider: str
    grounded: bool
    detail: str | None = None


def _step_from_dict(raw: dict[str, Any]) -> DeductionStep | None:
    step_id = str(raw.get("id") or "").strip()
    title = str(raw.get("title") or "").strip()
    value = str(raw.get("value") or "").strip()
    summary = str(raw.get("summary") or "").strip()
    details_raw = raw.get("details") or []
    if not step_id or not title:
        return None
    details: list[str] = []
    if isinstance(details_raw, list):
        for item in details_raw:
            text = str(item).strip()
            if text:
                details.append(text)
    return DeductionStep(
        id=step_id,
        title=title,
        value=value,
        summary=summary,
        details=tuple(details),
    )


def normalize_steps(raw_steps: list[dict[str, Any]]) -> tuple[DeductionStep, ...]:
    out: list[DeductionStep] = []
    for item in raw_steps:
        if not isinstance(item, dict):
            continue
        step = _step_from_dict(item)
        if step is not None:
            out.append(step)
    return tuple(out)


def _source_blob(step: DeductionStep) -> str:
    parts = [step.id, step.title, step.value, step.summary, *step.details]
    return "\n".join(parts)


def _text_is_grounded(text: str, allowed: set[str]) -> bool:
    formatted = format_currency_tokens_in_text(text.strip())
    novel = _extract_numeric_tokens(formatted) - allowed
    # Ignore lone single digits that often appear in "step 1" style wording
    novel = {token for token in novel if not re.fullmatch(r"\d", token)}
    return not novel


def merge_rephrased_steps(
    source: tuple[DeductionStep, ...],
    llm_steps: list[dict[str, Any]],
) -> tuple[DeductionStep, ...] | None:
    """Keep id/title/value from source; accept only grounded summary/details.

    Returns None if the LLM response shape is unusable (wrong count / missing ids).
    Per-step failures fall back to the original wording for that step.
    """
    if not source:
        return ()
    by_id: dict[str, dict[str, Any]] = {}
    for item in llm_steps:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"]).strip()] = item

    if not by_id:
        return None

    merged: list[DeductionStep] = []
    for step in source:
        candidate = by_id.get(step.id)
        if candidate is None:
            merged.append(step)
            continue
        allowed = _extract_numeric_tokens(_source_blob(step))
        summary = str(candidate.get("summary") or "").strip()
        details_raw = candidate.get("details") or []
        details: list[str] = []
        if isinstance(details_raw, list):
            for line in details_raw:
                text = str(line).strip()
                if text:
                    details.append(format_currency_tokens_in_text(text))

        if not summary or not _text_is_grounded(summary, allowed):
            merged.append(step)
            continue
        if any(not _text_is_grounded(line, allowed) for line in details):
            merged.append(step)
            continue
        if not details:
            merged.append(step)
            continue

        merged.append(
            DeductionStep(
                id=step.id,
                title=step.title,
                value=step.value,
                summary=format_currency_tokens_in_text(summary),
                details=tuple(details),
            )
        )
    return tuple(merged)


class DeductionRephraser:
    def __init__(self, http_client: Any, settings: Settings | None = None) -> None:
        self._client = http_client
        self._settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        provider = (self._settings.narrative_provider or "template").strip().lower()
        key = (self._settings.google_api_key or "").strip()
        return provider == "llm" and bool(key)

    async def rephrase(self, *, symbol: str, steps: tuple[DeductionStep, ...]) -> DeductionRephraseResult:
        if not steps:
            return DeductionRephraseResult(steps=(), provider="template", grounded=True)

        if not self.enabled:
            return DeductionRephraseResult(
                steps=steps,
                provider="template",
                grounded=True,
                detail="llm_disabled",
            )

        key = (self._settings.google_api_key or "").strip()
        model = (self._settings.gemini_model or "gemini-2.0-flash").strip()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )

        source_payload = [
            {
                "id": step.id,
                "title": step.title,
                "value": step.value,
                "summary": step.summary,
                "details": list(step.details),
            }
            for step in steps
        ]
        system = (
            "You rephrase TradePilot plan-deduction steps for beginners. "
            "STRICT RULES: "
            "1) Do not change strategy logic, conclusions, or recommendations. "
            "2) Do not invent, omit, round, or alter any number, price, percent, ratio, or share count. "
            "3) Do not add new levels, indicators, advice, or market opinions. "
            "4) Keep the same step ids and the same number of detail bullets per step when possible. "
            "5) Only improve clarity and presentability of the wording. "
            "Return JSON: {steps:[{id, summary, details:[...]}]}."
        )
        user = (
            f"Symbol={symbol.upper()}\n"
            f"Canonical steps JSON (source of truth):\n"
            f"{json.dumps(source_payload, ensure_ascii=True)}\n"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
            "generationConfig": {
                "temperature": 0.15,
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
            },
        }
        try:
            resp = await self._client.post(url, json=payload, timeout=25.0)
            status = getattr(resp, "status_code", None) or getattr(resp, "status", None)
            if status is None or int(status) >= 400:
                body_snip = ""
                try:
                    body_snip = str(resp.text)[:180]
                except Exception:
                    body_snip = ""
                return DeductionRephraseResult(
                    steps=steps,
                    provider="template",
                    grounded=True,
                    detail=f"gemini_http_{status} {body_snip}",
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
            llm_steps = parsed.get("steps") or []
            if not isinstance(llm_steps, list):
                return DeductionRephraseResult(
                    steps=steps,
                    provider="template",
                    grounded=True,
                    detail="gemini_bad_shape",
                )
            merged = merge_rephrased_steps(steps, llm_steps)
            if merged is None:
                return DeductionRephraseResult(
                    steps=steps,
                    provider="template",
                    grounded=True,
                    detail="gemini_ungrounded_or_empty",
                )
            changed = merged != steps
            return DeductionRephraseResult(
                steps=merged,
                provider="gemini" if changed else "template",
                grounded=True,
                detail=None if changed else "gemini_unchanged_or_all_rejected",
            )
        except Exception as exc:
            logger.warning("deduction.rephrase_failed: %s", exc)
            return DeductionRephraseResult(
                steps=steps,
                provider="template",
                grounded=True,
                detail=str(exc),
            )


__all__ = [
    "DeductionStep",
    "DeductionRephraseResult",
    "DeductionRephraser",
    "normalize_steps",
    "merge_rephrased_steps",
]
