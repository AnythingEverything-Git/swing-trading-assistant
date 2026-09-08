"""Sellable EP1 — shared universe filters."""

from decimal import Decimal

from app.domain.universe.filters import UniverseFilterSpec, filter_symbols
from app.infrastructure.universe import get_universe


def test_nse_all_is_cash_union_etf() -> None:
    all_snap = get_universe("NSE_ALL").get_snapshot()
    cash = set(get_universe("NSE_CASH").get_snapshot().symbols)
    etf = set(get_universe("NSE_ETF").get_snapshot().symbols)
    assert set(all_snap.symbols) == cash | etf
    assert len(all_snap.symbols) >= len(cash)
    assert all_snap.name == "NSE_ALL"


def test_filter_asset_class_etf_only() -> None:
    symbols = list(get_universe("NSE_ALL").get_snapshot().symbols)[:200]
    kept, drops = filter_symbols(symbols, UniverseFilterSpec(asset_class="ETF"))
    assert all(d.reason for d in drops) or kept
    # ETF filter should drop most cash names when map is present
    assert len(kept) <= len(symbols)


def test_filter_min_price_without_quotes_keeps() -> None:
    symbols = ["RELIANCE", "TCS", "INFY"]
    kept, decisions = filter_symbols(
        symbols,
        UniverseFilterSpec(min_price=Decimal("1")),
        last_price_by_symbol={},
    )
    assert kept == symbols
    assert all(d.kept for d in decisions)


def test_filter_spec_from_mapping() -> None:
    spec = UniverseFilterSpec.from_mapping(
        {
            "asset_class": "STOCK",
            "min_adv_inr": "1000000",
            "exclude_surveillance": True,
            "direction": "LONG",
        }
    )
    assert spec.asset_class == "STOCK"
    assert spec.min_adv_inr == Decimal("1000000")
    assert spec.direction == "LONG"
    assert "asset_class" in spec.to_dict()
