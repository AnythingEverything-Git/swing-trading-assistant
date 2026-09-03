"""NSE trading-symbol -> Upstox instrument_key mapping.

Keeps Upstox-specific identifiers in infrastructure. Application/domain layers
continue to use normal NSE symbols (e.g. RELIANCE).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.domain.universe import normalize_symbol
from app.infrastructure.market_data.upstox_provider import UpstoxAPIError

_DEFAULT_MAP_PATH = Path(__file__).resolve().parent / "data" / "nse_upstox_instrument_keys.json"


class FileBackedInstrumentKeyMap:
    """Deterministic, replaceable symbol -> instrument_key resolver.

    Usable as the `instrument_key_map` callable for `UpstoxMarketDataProvider`.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else _DEFAULT_MAP_PATH
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"instrument key map must be a JSON object: {self._path}")
        mappings = raw.get("mappings")
        if not isinstance(mappings, dict):
            raise ValueError("instrument key map requires a 'mappings' object")

        normalized: dict[str, str] = {}
        for symbol, instrument_key in mappings.items():
            key = normalize_symbol(str(symbol))
            value = str(instrument_key).strip()
            if not value:
                raise ValueError(f"instrument_key for {key} must be a non-empty string")
            normalized[key] = value
        self._mappings = normalized
        self.version = str(raw.get("version") or "").strip() or None

    def resolve(self, symbol: str) -> str:
        normalized = normalize_symbol(symbol)
        try:
            return self._mappings[normalized]
        except KeyError as exc:
            raise UpstoxAPIError(f"Instrument mapping missing for symbol: {normalized}") from exc

    def __call__(self, symbol: str) -> str:
        return self.resolve(symbol)

    def __contains__(self, symbol: object) -> bool:
        if not isinstance(symbol, str):
            return False
        try:
            return normalize_symbol(symbol) in self._mappings
        except (TypeError, ValueError):
            return False

    def __len__(self) -> int:
        return len(self._mappings)


def load_default_nse_instrument_key_map() -> FileBackedInstrumentKeyMap:
    """Load the packaged demo/development NSE -> Upstox instrument key map."""
    return FileBackedInstrumentKeyMap()


__all__ = ["FileBackedInstrumentKeyMap", "load_default_nse_instrument_key_map"]
