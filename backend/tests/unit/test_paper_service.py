"""Unit tests for PaperTradeService pending entry fills and tick exits."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.application.paper import PaperTradeService
from app.domain.paper import PaperTrade, entry_reached


class FakeRepo:
    def __init__(self) -> None:
        self.trades: list[PaperTrade] = []
        self._next_id = 1

    async def list_active_symbols(self) -> set[str]:
        return {t.symbol for t in self.trades if t.status in {"PENDING", "OPEN"}}

    async def list_open_symbols(self) -> set[str]:
        return await self.list_active_symbols()

    async def create(self, trade: PaperTrade) -> PaperTrade:
        trade.id = self._next_id
        self._next_id += 1
        self.trades.append(trade)
        return trade

    async def save(self, trade: PaperTrade) -> PaperTrade:
        for idx, existing in enumerate(self.trades):
            if existing.id == trade.id:
                self.trades[idx] = trade
                return trade
        self.trades.append(trade)
        return trade

    async def get_by_id(self, trade_id: int) -> PaperTrade | None:
        for trade in self.trades:
            if trade.id == trade_id:
                return trade
        return None

    async def list_open(self) -> list[PaperTrade]:
        return [t for t in self.trades if t.status == "OPEN"]

    async def list_active(self) -> list[PaperTrade]:
        return [t for t in self.trades if t.status in {"PENDING", "OPEN"}]

    async def list_by_status(self, status: str | None = None, *, limit: int = 200) -> list[PaperTrade]:
        if status is None or status == "ALL":
            return list(self.trades)[:limit]
        if status == "ACTIVE":
            return [t for t in self.trades if t.status in {"PENDING", "OPEN"}][:limit]
        return [t for t in self.trades if t.status == status][:limit]


class FakeQuotes:
    def __init__(self, prices: dict[str, str]) -> None:
        self.prices = prices

    async def get_last_traded_prices(self, symbols: list[str]) -> dict:
        return {
            symbol: {"last_price": Decimal(self.prices[symbol])}
            for symbol in symbols
            if symbol in self.prices
        }


def _opp(symbol: str, qty: int | None, direction: str = "LONG") -> SimpleNamespace:
    if direction == "LONG":
        candidate = SimpleNamespace(
            direction="LONG",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            target=Decimal("110"),
            setup_name="BreakoutRetestConfirmation",
        )
    else:
        candidate = SimpleNamespace(
            direction="SHORT",
            entry_price=Decimal("100"),
            stop_loss=Decimal("105"),
            target=Decimal("90"),
            setup_name="BreakdownRetestConfirmation",
        )
    return SimpleNamespace(
        symbol=symbol,
        quantity=qty,
        risk_amount=Decimal("50") if qty else None,
        quality_score=Decimal("70"),
        candidate=candidate,
    )


def test_entry_reached_long_and_short():
    assert entry_reached(direction="LONG", mark=Decimal("100"), entry=Decimal("100"))
    assert entry_reached(direction="LONG", mark=Decimal("101"), entry=Decimal("100"))
    assert not entry_reached(direction="LONG", mark=Decimal("99"), entry=Decimal("100"))
    assert entry_reached(direction="SHORT", mark=Decimal("100"), entry=Decimal("100"))
    assert entry_reached(direction="SHORT", mark=Decimal("99"), entry=Decimal("100"))
    assert not entry_reached(direction="SHORT", mark=Decimal("101"), entry=Decimal("100"))


@pytest.mark.asyncio
async def test_open_from_scan_creates_pending_and_skips_duplicates():
    repo = FakeRepo()
    svc = PaperTradeService(repo)  # type: ignore[arg-type]
    scan = SimpleNamespace(
        scan_run_id=7,
        opportunities=[
            _opp("AAA", 10),
            _opp("BBB", 0),
            _opp("CCC", None),
            _opp("AAA", 5),
        ],
    )
    result = await svc.open_from_scan(scan)
    assert result.opened == 1
    assert result.skipped_qty == 2
    assert result.skipped_open == 1
    assert len(repo.trades) == 1
    assert repo.trades[0].symbol == "AAA"
    assert repo.trades[0].status == "PENDING"
    assert repo.trades[0].scan_run_id == 7


@pytest.mark.asyncio
async def test_tick_fills_pending_when_entry_reached_then_marks():
    repo = FakeRepo()
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=10,
        risk_amount=Decimal("50"),
        status="PENDING",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    await repo.create(trade)
    svc = PaperTradeService(repo, FakeQuotes({"INFY": "101"}))  # type: ignore[arg-type]
    result = await svc.tick()
    assert len(result.filled_this_tick) == 1
    assert result.filled_this_tick[0].status == "OPEN"
    assert result.open_trades[0].unrealized_pnl == Decimal("10")
    assert result.pending_trades == []


@pytest.mark.asyncio
async def test_tick_keeps_pending_until_entry():
    repo = FakeRepo()
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=10,
        risk_amount=Decimal("50"),
        status="PENDING",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    await repo.create(trade)
    svc = PaperTradeService(repo, FakeQuotes({"INFY": "98"}))  # type: ignore[arg-type]
    result = await svc.tick()
    assert result.filled_this_tick == []
    assert len(result.pending_trades) == 1
    assert result.pending_trades[0].status == "PENDING"
    assert result.pending_trades[0].last_mark_price == Decimal("98")


@pytest.mark.asyncio
async def test_tick_fill_then_target_same_tick_on_gap():
    repo = FakeRepo()
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=10,
        risk_amount=Decimal("50"),
        status="PENDING",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    await repo.create(trade)
    # Gap through entry straight to/through target — fill then target same tick.
    svc = PaperTradeService(repo, FakeQuotes({"INFY": "112"}))  # type: ignore[arg-type]
    result = await svc.tick()
    assert result.filled_this_tick == []
    assert len(result.closed_this_tick) == 1
    assert result.closed_this_tick[0].exit_reason == "TARGET"


@pytest.mark.asyncio
async def test_tick_closes_long_on_stop():
    repo = FakeRepo()
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=10,
        risk_amount=Decimal("50"),
        status="OPEN",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    await repo.create(trade)
    svc = PaperTradeService(repo, FakeQuotes({"INFY": "94"}))  # type: ignore[arg-type]
    result = await svc.tick()
    assert len(result.closed_this_tick) == 1
    assert result.closed_this_tick[0].exit_reason == "STOP_LOSS"
    assert result.open_trades == []


@pytest.mark.asyncio
async def test_tick_marks_unrealized_for_short():
    repo = FakeRepo()
    trade = PaperTrade(
        symbol="TCS",
        direction="SHORT",
        entry_price=Decimal("100"),
        stop_loss=Decimal("105"),
        target=Decimal("90"),
        quantity=5,
        risk_amount=Decimal("25"),
        status="OPEN",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    await repo.create(trade)
    svc = PaperTradeService(repo, FakeQuotes({"TCS": "98"}))  # type: ignore[arg-type]
    result = await svc.tick()
    assert len(result.open_trades) == 1
    assert result.open_trades[0].unrealized_pnl == Decimal("10")


@pytest.mark.asyncio
async def test_cancel_pending():
    repo = FakeRepo()
    trade = PaperTrade(
        symbol="INFY",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        target=Decimal("110"),
        quantity=10,
        risk_amount=Decimal("50"),
        status="PENDING",
        opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    await repo.create(trade)
    svc = PaperTradeService(repo)  # type: ignore[arg-type]
    closed = await svc.close_manual(1)
    assert closed.status == "CLOSED"
    assert closed.exit_reason == "CANCELLED"
    assert closed.realized_pnl == Decimal("0")
