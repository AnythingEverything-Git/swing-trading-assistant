"""Probe Gemini models using repo settings (does not print secrets)."""
from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import httpx

from app.application.narrative.gemini_narrator import GeminiNarrator
from app.core.config import get_settings


def _run(coro):
    if sys.platform.startswith("win"):
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


async def main() -> None:
    settings = get_settings()
    key = (settings.google_api_key or "").strip()
    print("provider", settings.narrative_provider)
    print("configured_model", settings.gemini_model)
    print("key_set", bool(key))
    print("key_prefix", key[:4] if key else "")

    models = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-flash-latest",
    ]
    working: list[str] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        list_resp = await client.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        )
        print("list_status", list_resp.status_code)
        if list_resp.status_code == 200:
            flash = [
                m.get("name")
                for m in list_resp.json().get("models", [])
                if "flash" in (m.get("name") or "").lower()
            ]
            print("flash_models_count", len(flash))
            for name in flash[:15]:
                print("-", name)
        else:
            print("list_error", list_resp.text[:240])

        payload = {
            "contents": [{"role": "user", "parts": [{"text": 'Return JSON {"ok":true}'}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        for model in models:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={key}"
            )
            resp = await client.post(url, json=payload)
            ok = resp.status_code < 400
            print(model, resp.status_code, "ok" if ok else resp.text[:140])
            if ok:
                working.append(model)

        chosen = working[0] if working else settings.gemini_model
        if working:
            print("using", chosen)
            # Temporarily override model for narrator test
            object.__setattr__(settings, "gemini_model", chosen) if False else None
            settings.__dict__["gemini_model"] = chosen
            narrator = GeminiNarrator(client, settings)
            result = await narrator.generate_insight(
                tab="overview",
                context={
                    "symbol": "INFY",
                    "performance": [
                        {"label": "1D", "change_percent": "1.25"},
                        {"label": "1W", "change_percent": "-0.80"},
                    ],
                    "high_52w": "1980.00",
                    "low_52w": "1350.00",
                    "last_close": "1520.00",
                    "setup": {
                        "narrative": "INFY confirmed breakout with entry 1520.00 stop 1485.00 target 1590.00",
                        "entry": "1520.00",
                        "stop": "1485.00",
                        "target": "1590.00",
                    },
                },
            )
            print("insight_provider", result.provider)
            print("insight_grounded", result.grounded)
            print("insight_detail", result.detail)
            print("insight_title", result.title)
            for bullet in result.bullets:
                print("-", bullet)
        else:
            print("NO_WORKING_MODEL")


if __name__ == "__main__":
    _run(main())
