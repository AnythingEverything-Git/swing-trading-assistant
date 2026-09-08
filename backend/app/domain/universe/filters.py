"""Shared in-app universe filters for Swing + Intraday (sellable EP1)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Sequence

from app.domain.intraday.asset_class import classify_asset_class, sector_map
from app.domain.intraday.eligibility import (
    is_corporate_action_blocked,
    is_surveillance_blocked,
)

AssetClassFilter = Literal["ALL", "STOCK", "ETF"]
DirectionFilter = Literal["ALL", "LONG", "SHORT"]


@dataclass(frozen=True)
class UniverseFilterSpec:
    """Pre-strategy filters applied to NSE_ALL (or any universe snapshot)."""

    asset_class: AssetClassFilter = "ALL"
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    min_adv_inr: Decimal | None = None
    sectors: tuple[str, ...] = ()
    exclude_surveillance: bool = True
    exclude_corporate_actions: bool = True
    direction: DirectionFilter = "ALL"  # applied post-strategy for swing; documented for UI

    @staticmethod
    def from_mapping(raw: dict | None) -> "UniverseFilterSpec":
        if not raw:
            return UniverseFilterSpec()
        sectors_raw = raw.get("sectors") or []
        sectors = tuple(str(s).strip() for s in sectors_raw if str(s).strip())
        ac = str(raw.get("asset_class") or "ALL").upper()
        if ac not in {"ALL", "STOCK", "ETF"}:
            ac = "ALL"
        direction = str(raw.get("direction") or "ALL").upper()
        if direction not in {"ALL", "LONG", "SHORT"}:
            direction = "ALL"

        def _dec(key: str) -> Decimal | None:
            val = raw.get(key)
            if val is None or val == "":
                return None
            return Decimal(str(val))

        return UniverseFilterSpec(
            asset_class=ac,  # type: ignore[arg-type]
            min_price=_dec("min_price"),
            max_price=_dec("max_price"),
            min_adv_inr=_dec("min_adv_inr"),
            sectors=sectors,
            exclude_surveillance=bool(raw.get("exclude_surveillance", True)),
            exclude_corporate_actions=bool(raw.get("exclude_corporate_actions", True)),
            direction=direction,  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict:
        return {
            "asset_class": self.asset_class,
            "min_price": str(self.min_price) if self.min_price is not None else None,
            "max_price": str(self.max_price) if self.max_price is not None else None,
            "min_adv_inr": str(self.min_adv_inr) if self.min_adv_inr is not None else None,
            "sectors": list(self.sectors),
            "exclude_surveillance": self.exclude_surveillance,
            "exclude_corporate_actions": self.exclude_corporate_actions,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class FilterDecision:
    symbol: str
    kept: bool
    reason: str | None = None


def filter_symbols(
    symbols: Sequence[str],
    spec: UniverseFilterSpec,
    *,
    session_date: date | None = None,
    last_price_by_symbol: dict[str, Decimal] | None = None,
    adv_by_symbol: dict[str, Decimal] | None = None,
) -> tuple[list[str], list[FilterDecision]]:
    """Return kept symbols + per-symbol decisions for coverage UI."""
    day = session_date or date.today()
    prices = last_price_by_symbol or {}
    advs = adv_by_symbol or {}
    sectors = sector_map()
    sector_allow = {s.upper() for s in spec.sectors} if spec.sectors else None

    kept: list[str] = []
    decisions: list[FilterDecision] = []

    for raw in symbols:
        sym = str(raw).strip().upper()
        if not sym:
            continue
        ac = classify_asset_class(sym)
        if spec.asset_class != "ALL" and ac != spec.asset_class:
            decisions.append(FilterDecision(sym, False, "ASSET_CLASS"))
            continue
        if sector_allow is not None:
            sec = (sectors.get(sym) or "UNKNOWN").upper()
            if sec not in sector_allow and "UNKNOWN" not in sector_allow:
                decisions.append(FilterDecision(sym, False, "SECTOR"))
                continue
        if spec.exclude_surveillance and is_surveillance_blocked(sym, session_date=day):
            decisions.append(FilterDecision(sym, False, "SURVEILLANCE"))
            continue
        if spec.exclude_corporate_actions and is_corporate_action_blocked(sym, day):
            decisions.append(FilterDecision(sym, False, "CORPORATE_ACTION"))
            continue
        px = prices.get(sym)
        if px is not None:
            if spec.min_price is not None and px < spec.min_price:
                decisions.append(FilterDecision(sym, False, "MIN_PRICE"))
                continue
            if spec.max_price is not None and px > spec.max_price:
                decisions.append(FilterDecision(sym, False, "MAX_PRICE"))
                continue
        adv = advs.get(sym)
        if adv is not None and spec.min_adv_inr is not None and adv < spec.min_adv_inr:
            decisions.append(FilterDecision(sym, False, "MIN_ADV"))
            continue
        kept.append(sym)
        decisions.append(FilterDecision(sym, True, None))

    return kept, decisions


FILTER_PRESETS: dict[str, UniverseFilterSpec] = {
    "liquid_large_cap": UniverseFilterSpec(
        asset_class="STOCK",
        min_adv_inr=Decimal("200000000"),
        min_price=Decimal("50"),
    ),
    "etf_only": UniverseFilterSpec(asset_class="ETF"),
    "high_liquidity": UniverseFilterSpec(min_adv_inr=Decimal("100000000")),
}


__all__ = [
    "AssetClassFilter",
    "DirectionFilter",
    "UniverseFilterSpec",
    "FilterDecision",
    "filter_symbols",
    "FILTER_PRESETS",
]
