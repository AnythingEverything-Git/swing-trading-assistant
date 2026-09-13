"""Seed and tick intraday ORB practice trades from a session run."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.intraday.practice import IntradayPracticeTrade
from app.infrastructure.database.repositories.intraday_practice_repository import (
    IntradayPracticeRepository,
)

IST = ZoneInfo("Asia/Kolkata")


def trade_to_dict(trade: IntradayPracticeTrade) -> dict[str, Any]:
    return {
        "id": trade.id,
        "session_id": trade.session_id,
        "session_date": trade.session_date.isoformat(),
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_price": str(trade.entry_price),
        "stop_loss": str(trade.stop_loss),
        "quantity": trade.quantity,
        "risk_amount": str(trade.risk_amount) if trade.risk_amount is not None else None,
        "status": trade.status,
        "opened_at": trade.opened_at.isoformat() if trade.opened_at else None,
        "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
        "exit_price": str(trade.exit_price) if trade.exit_price is not None else None,
        "exit_reason": trade.exit_reason,
        "last_mark_price": str(trade.last_mark_price) if trade.last_mark_price is not None else None,
        "unrealized_pnl": str(trade.unrealized_pnl) if trade.unrealized_pnl is not None else None,
        "realized_pnl": str(trade.realized_pnl) if trade.realized_pnl is not None else None,
        "strategy_id": trade.strategy_id,
        "config_hash": trade.config_hash,
    }


class IntradayPracticeService:
    def __init__(self, repository: IntradayPracticeRepository) -> None:
        self.repository = repository

    async def seed_from_session_payload(
        self,
        *,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Open practice trades from session fills (already filled at entry)."""
        fills = payload.get("fills") or []
        session_date = date.fromisoformat(str(payload["session_date"]))
        strategy_id = str(payload.get("strategy_id") or "NSE_STOCKS_ETF_ORB_RVOL_5M_V1")
        config_hash = str(payload.get("config_hash") or "CONFIG_V1")
        active = await self.repository.list_active_symbols(session_id)
        opened = 0
        skipped = 0
        locked = 0
        now = datetime.now(tz=IST)
        trades: list[IntradayPracticeTrade] = []

        from app.domain.intraday.config_v1 import DEFAULT_CONFIG_V1
        from app.domain.intraday.sizing import can_open
        from app.domain.intraday.types import FillPlan, PortfolioState

        equity = Decimal(str(payload.get("equity") or "1000000"))
        state = PortfolioState(equity=equity)
        # Rank-order fills the same way the engine armed them.
        ordered_fills = sorted(fills, key=lambda f: (int(f.get("rank") or 999), str(f.get("symbol") or "")))

        for fill in ordered_fills:
            symbol = str(fill.get("symbol", "")).upper().strip()
            if not symbol or symbol in active:
                skipped += 1
                continue
            qty = int(fill.get("quantity") or 0)
            if qty <= 0:
                skipped += 1
                continue
            plan = FillPlan(
                symbol=symbol,
                direction=str(fill.get("direction") or "LONG"),  # type: ignore[arg-type]
                rank=int(fill.get("rank") or 0),
                entry=Decimal(str(fill["entry"])),
                stop=Decimal(str(fill["stop"])),
                quantity=qty,
                stop_distance=Decimal(str(fill.get("stop_distance") or "0")),
                effective_risk_per_share=Decimal(str(fill.get("effective_risk_per_share") or "0")),
                trigger_bar_open=now,
                risk_amount=Decimal(str(fill["risk_amount"])) if fill.get("risk_amount") else Decimal("0"),
            )
            lock = can_open(state, plan, DEFAULT_CONFIG_V1)
            if lock:
                locked += 1
                skipped += 1
                continue
            trade = IntradayPracticeTrade(
                symbol=symbol,
                direction=str(fill.get("direction") or "LONG"),  # type: ignore[arg-type]
                entry_price=Decimal(str(fill["entry"])),
                stop_loss=Decimal(str(fill["stop"])),
                quantity=qty,
                risk_amount=Decimal(str(fill["risk_amount"])) if fill.get("risk_amount") else None,
                session_date=session_date,
                session_id=session_id,
                status="OPEN",
                opened_at=now,
                last_mark_price=Decimal(str(fill["entry"])),
                unrealized_pnl=Decimal("0"),
                strategy_id=strategy_id,
                config_hash=config_hash,
            )
            await self.repository.create(trade)
            active.add(symbol)
            state.open_fills.append(plan)
            state.traded_symbols.add(symbol)
            opened += 1
            trades.append(trade)

        return {
            "opened": opened,
            "skipped": skipped,
            "locked": locked,
            "claim": "INTRADAY PRACTICE — fake money · stop or 15:10 flatten · no profit goal · CONFIG_V1 portfolio locks on seed",
            "trades": [trade_to_dict(t) for t in trades],
        }

    async def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return [trade_to_dict(t) for t in await self.repository.list_by_session(session_id)]

    async def tick(
        self,
        *,
        session_id: str | None = None,
        marks: dict[str, Decimal] | None = None,
        now: datetime | None = None,
        force_eod: bool = False,
        quote_provider: Any | None = None,
    ) -> dict[str, Any]:
        """Mark open trades. Prefer live LTP when quote_provider is set and marks omitted."""
        stamp = now or datetime.now(tz=IST)
        if force_eod:
            stamp = stamp.astimezone(IST).replace(hour=15, minute=11, second=0, microsecond=0)

        if session_id:
            open_trades = [
                t for t in await self.repository.list_by_session(session_id) if t.status == "OPEN"
            ]
        else:
            open_trades = await self.repository.list_open()

        resolved_marks = dict(marks or {})
        quote_source = "manual"
        if quote_provider is not None and open_trades:
            symbols = [t.symbol for t in open_trades if t.symbol not in resolved_marks]
            if symbols:
                quote_fn = getattr(quote_provider, "get_last_traded_prices", None)
                if quote_fn is not None:
                    try:
                        quotes = await quote_fn(symbols)
                        for sym in symbols:
                            q = quotes.get(sym) or quotes.get(sym.upper()) or {}
                            raw = q.get("last_price", q.get("ltp", q.get("current_price")))
                            if raw is not None:
                                resolved_marks[sym] = Decimal(str(raw))
                        quote_source = "live_ltp"
                    except Exception:  # noqa: BLE001 — fall back to last mark
                        quote_source = "quote_error_fallback"

        closed: list[dict[str, Any]] = []
        marked = 0
        for trade in open_trades:
            mark = resolved_marks.get(trade.symbol)
            if mark is None and trade.last_mark_price is not None:
                mark = trade.last_mark_price
            if mark is None:
                continue
            before = trade.status
            trade.apply_mark(mark, now=stamp)
            await self.repository.save(trade)
            marked += 1
            if before == "OPEN" and trade.status == "CLOSED":
                closed.append(trade_to_dict(trade))

        return {
            "marks_applied": marked,
            "closed_this_tick": closed,
            "open_count": sum(1 for t in open_trades if t.status == "OPEN"),
            "quote_source": quote_source,
            "claim": "INTRADAY PRACTICE — fake money · stop or 15:10 flatten · no profit goal",
        }

    async def divergence_vs_session(
        self,
        *,
        session_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare practice closed trades to model closed trades for the same session."""
        practice = await self.repository.list_by_session(session_id)
        model_by_sym = {
            str(t.get("symbol")).upper(): t for t in (payload.get("closed_trades") or []) if t.get("symbol")
        }
        rows: list[dict[str, Any]] = []
        matched = 0
        pnl_gap = Decimal("0")
        for trade in practice:
            model = model_by_sym.get(trade.symbol)
            if model is None:
                rows.append(
                    {
                        "symbol": trade.symbol,
                        "practice_status": trade.status,
                        "model_status": "missing",
                        "practice_pnl": str(trade.realized_pnl) if trade.realized_pnl is not None else None,
                        "model_pnl": None,
                        "pnl_gap": None,
                        "exit_match": False,
                    }
                )
                continue
            model_pnl = Decimal(str(model.get("pnl") or "0"))
            practice_pnl = trade.realized_pnl if trade.realized_pnl is not None else Decimal("0")
            gap = practice_pnl - model_pnl
            pnl_gap += gap
            exit_match = (trade.exit_reason or "") == str(model.get("exit_reason") or "")
            if trade.status == "CLOSED":
                matched += 1
            rows.append(
                {
                    "symbol": trade.symbol,
                    "practice_status": trade.status,
                    "model_status": "CLOSED",
                    "practice_pnl": str(practice_pnl),
                    "model_pnl": str(model_pnl),
                    "pnl_gap": str(gap),
                    "exit_match": exit_match,
                    "practice_exit": trade.exit_reason,
                    "model_exit": model.get("exit_reason"),
                }
            )
        return {
            "session_id": session_id,
            "matched_closed": matched,
            "total_practice": len(practice),
            "total_model_closed": len(model_by_sym),
            "pnl_gap_sum": str(pnl_gap),
            "rows": rows,
            "note": "Gaps are expected when practice marks use live LTP vs model 1m path.",
        }

    async def close_manual(self, trade_id: int, price: Decimal) -> dict[str, Any]:
        trade = await self.repository.get(trade_id)
        if trade is None:
            raise ValueError("Practice trade not found")
        trade.close_manual(price, now=datetime.now(tz=IST))
        await self.repository.save(trade)
        return trade_to_dict(trade)

    async def reset_all(self) -> int:
        return await self.repository.delete_all()


__all__ = ["IntradayPracticeService", "trade_to_dict"]
