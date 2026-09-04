"""Paper trading application service — simulated fills only."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from app.domain.paper import PaperTrade, entry_reached
from app.infrastructure.database.repositories.paper_trade_repository import PaperTradeRepository


class QuoteProvider(Protocol):
    async def get_last_traded_prices(self, symbols: list[str]) -> dict[str, dict[str, Any]]: ...


@dataclass(frozen=True)
class OpenFromScanResult:
    opened: int  # pending watches created (kept name for scan response field)
    skipped_qty: int
    skipped_open: int


@dataclass
class PaperTickResult:
    pending_trades: list[PaperTrade] = field(default_factory=list)
    open_trades: list[PaperTrade] = field(default_factory=list)
    filled_this_tick: list[PaperTrade] = field(default_factory=list)
    closed_this_tick: list[PaperTrade] = field(default_factory=list)
    marks_applied: int = 0


@dataclass(frozen=True)
class PaperSummary:
    pending_count: int
    open_count: int
    closed_count: int
    total_unrealized: Decimal
    total_realized: Decimal
    winning_closed: int
    losing_closed: int
    claim: str = "PRACTICE TRADES ONLY — fake money, no real broker orders"


class PaperTradeService:
    def __init__(self, repository: PaperTradeRepository, quote_provider: QuoteProvider | None = None) -> None:
        self.repository = repository
        self.quote_provider = quote_provider

    async def open_from_scan(self, scan_payload: Any) -> OpenFromScanResult:
        """Create PENDING watches for every eligible with quantity > 0.

        Fills only later when live price reaches entry (see tick).
        """
        opportunities = getattr(scan_payload, "opportunities", None) or []
        scan_run_id = getattr(scan_payload, "scan_run_id", None)
        active_symbols = await self.repository.list_active_symbols()
        opened = 0
        skipped_qty = 0
        skipped_open = 0
        now = datetime.now(timezone.utc)

        for item in opportunities:
            quantity = getattr(item, "quantity", None)
            if quantity is None or int(quantity) <= 0:
                skipped_qty += 1
                continue
            symbol = str(getattr(item, "symbol", "")).upper().strip()
            if not symbol:
                skipped_qty += 1
                continue
            if symbol in active_symbols:
                skipped_open += 1
                continue
            candidate = getattr(item, "candidate", None)
            if candidate is None:
                skipped_qty += 1
                continue
            direction = getattr(candidate, "direction", "LONG")
            trade = PaperTrade(
                symbol=symbol,
                direction=direction,
                entry_price=Decimal(str(candidate.entry_price)),
                stop_loss=Decimal(str(candidate.stop_loss)),
                target=Decimal(str(candidate.target)),
                quantity=int(quantity),
                risk_amount=None
                if getattr(item, "risk_amount", None) is None
                else Decimal(str(item.risk_amount)),
                status="PENDING",
                opened_at=now,
                scan_run_id=scan_run_id,
                setup_name=getattr(candidate, "setup_name", None),
                quality_score=None
                if getattr(item, "quality_score", None) is None
                else Decimal(str(item.quality_score)),
                last_mark_price=None,
                unrealized_pnl=None,
                updated_at=now,
            )
            await self.repository.create(trade)
            active_symbols.add(symbol)
            opened += 1

        return OpenFromScanResult(opened=opened, skipped_qty=skipped_qty, skipped_open=skipped_open)

    def _quote_price(self, quotes: dict[str, dict[str, Any]], symbol: str) -> Decimal | None:
        quote = quotes.get(symbol) or quotes.get(symbol.upper())
        if not isinstance(quote, dict):
            return None
        raw = quote.get("ltp", quote.get("current_price", quote.get("last_price")))
        if raw is None:
            return None
        mark = Decimal(str(raw))
        return mark if mark > 0 else None

    async def tick(self) -> PaperTickResult:
        active = await self.repository.list_active()
        if not active:
            return PaperTickResult()

        quotes: dict[str, dict[str, Any]] = {}
        if self.quote_provider is not None:
            symbols = [trade.symbol for trade in active]
            try:
                quotes = await self.quote_provider.get_last_traded_prices(symbols)
            except Exception:
                quotes = {}

        pending_trades: list[PaperTrade] = []
        open_trades: list[PaperTrade] = []
        filled_this_tick: list[PaperTrade] = []
        closed_this_tick: list[PaperTrade] = []
        marks = 0
        now = datetime.now(timezone.utc)

        for trade in active:
            mark = self._quote_price(quotes, trade.symbol)
            if mark is None:
                if trade.status == "PENDING":
                    pending_trades.append(trade)
                else:
                    open_trades.append(trade)
                continue

            if trade.status == "PENDING":
                trade.last_mark_price = mark
                trade.updated_at = now
                if entry_reached(direction=trade.direction, mark=mark, entry=trade.entry_price):
                    trade.activate_at_entry(now=now)
                    # After fill, mark with live LTP so stop/target can fire same tick if gapped.
                    decision = trade.apply_mark(mark, now=now)
                    marks += 1
                    await self.repository.save(trade)
                    if decision.should_exit:
                        closed_this_tick.append(trade)
                    else:
                        filled_this_tick.append(trade)
                        open_trades.append(trade)
                else:
                    await self.repository.save(trade)
                    pending_trades.append(trade)
                continue

            # OPEN
            decision = trade.apply_mark(mark, now=now)
            marks += 1
            await self.repository.save(trade)
            if decision.should_exit:
                closed_this_tick.append(trade)
            else:
                open_trades.append(trade)

        return PaperTickResult(
            pending_trades=pending_trades,
            open_trades=open_trades,
            filled_this_tick=filled_this_tick,
            closed_this_tick=closed_this_tick,
            marks_applied=marks,
        )

    async def close_manual(self, trade_id: int, price: Decimal | None = None) -> PaperTrade:
        trade = await self.repository.get_by_id(trade_id)
        if trade is None:
            raise ValueError("paper trade not found")
        if trade.status == "CLOSED":
            raise ValueError("paper trade is already closed")
        if trade.status == "PENDING":
            trade.close_manual(Decimal("0"))
            return await self.repository.save(trade)
        mark = price
        if mark is None:
            mark = trade.last_mark_price or trade.entry_price
            if self.quote_provider is not None:
                try:
                    quotes = await self.quote_provider.get_last_traded_prices([trade.symbol])
                    live = self._quote_price(quotes, trade.symbol)
                    if live is not None:
                        mark = live
                except Exception:
                    pass
        assert mark is not None
        trade.close_manual(mark)
        return await self.repository.save(trade)

    async def list_trades(self, status: str = "ALL") -> list[PaperTrade]:
        return await self.repository.list_by_status(status if status else "ALL")

    async def summary(self) -> PaperSummary:
        pending_trades = await self.repository.list_by_status("PENDING")
        open_trades = await self.repository.list_by_status("OPEN")
        closed_trades = await self.repository.list_by_status("CLOSED", limit=500)
        total_unrealized = sum((t.unrealized_pnl or Decimal("0") for t in open_trades), Decimal("0"))
        total_realized = sum((t.realized_pnl or Decimal("0") for t in closed_trades), Decimal("0"))
        winning = sum(1 for t in closed_trades if (t.realized_pnl or Decimal("0")) > 0)
        losing = sum(1 for t in closed_trades if (t.realized_pnl or Decimal("0")) < 0)
        return PaperSummary(
            pending_count=len(pending_trades),
            open_count=len(open_trades),
            closed_count=len(closed_trades),
            total_unrealized=total_unrealized,
            total_realized=total_realized,
            winning_closed=winning,
            losing_closed=losing,
        )
