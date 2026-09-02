from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.deps import get_backtest_service
from app.api.main import create_app
from app.application.backtesting.backtest_models import BacktestResult, BacktestTrade, ExitReason


def make_result():
    trade_time = datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc)
    trade = BacktestTrade(
        symbol="TST",
        timeframe="1d",
        setup_time=trade_time,
        entry_time=trade_time,
        entry_price=Decimal("100"),
        stop_loss=Decimal("98"),
        target=Decimal("105"),
        exit_time=trade_time,
        exit_price=Decimal("105"),
        exit_reason=ExitReason.TARGET,
        risk_per_share=Decimal("2"),
        r_multiple=Decimal("2.5"),
        pnl_per_share=Decimal("5"),
        quantity=50,
    )
    return BacktestResult(
        symbol="TST",
        timeframe="1d",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        trades=(trade,),
    )


class FakeBacktestService:
    def __init__(self, result):
        self.result = result

    async def run(self, *args):
        return self.result


def test_backtest_api_returns_completed_trade():
    app = create_app()
    app.dependency_overrides[get_backtest_service] = lambda: FakeBacktestService(make_result())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TST",
                "timeframe": "1d",
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-01-31T00:00:00Z",
                "account_equity": "10000",
                "risk_percent": "1",
            },
        )

    assert response.status_code == 200
    assert response.json()["completed_trades"] == 1
    assert response.json()["trades"][0]["quantity"] == 50
    assert response.json()["trades"][0]["risk_amount"] == "100"
    assert response.json()["trades"][0]["pnl"] == "250"


def test_backtest_api_returns_empty_trade_list():
    result = make_result()
    empty_result = BacktestResult(
        symbol=result.symbol,
        timeframe=result.timeframe,
        start=result.start,
        end=result.end,
        trades=(),
    )
    app = create_app()
    app.dependency_overrides[get_backtest_service] = lambda: FakeBacktestService(empty_result)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TST",
                "timeframe": "1d",
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-01-31T00:00:00Z",
                "account_equity": "10000",
                "risk_percent": "1",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"symbol": "TST", "timeframe": "1d", "completed_trades": 0, "trades": []}


def test_backtest_api_rejects_invalid_date_range():
    app = create_app()
    app.dependency_overrides[get_backtest_service] = lambda: FakeBacktestService(make_result())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TST",
                "timeframe": "1d",
                "start": "2024-02-01T00:00:00Z",
                "end": "2024-01-01T00:00:00Z",
                "account_equity": "10000",
                "risk_percent": "1",
            },
        )

    assert response.status_code == 400


def test_backtest_api_rejects_non_positive_risk_inputs_without_signals():
    app = create_app()
    app.dependency_overrides[get_backtest_service] = lambda: FakeBacktestService(
        BacktestResult(
            symbol="TST",
            timeframe="1d",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 31, tzinfo=timezone.utc),
            trades=(),
        )
    )

    base_payload = {
        "symbol": "TST",
        "timeframe": "1d",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-01-31T00:00:00Z",
        "account_equity": "10000",
        "risk_percent": "1",
    }
    invalid_payloads = [
        {**base_payload, "account_equity": "0"},
        {**base_payload, "account_equity": "-1"},
        {**base_payload, "risk_percent": "0"},
        {**base_payload, "risk_percent": "-1"},
    ]

    with TestClient(app) as client:
        responses = [client.post("/api/v1/backtest/run", json=payload) for payload in invalid_payloads]

    assert all(response.status_code == 422 for response in responses)


def test_backtest_api_output_is_deterministic():
    app = create_app()
    app.dependency_overrides[get_backtest_service] = lambda: FakeBacktestService(make_result())
    payload = {
        "symbol": "TST",
        "timeframe": "1d",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-01-31T00:00:00Z",
        "account_equity": "10000",
        "risk_percent": "1",
    }

    with TestClient(app) as client:
        first = client.post("/api/v1/backtest/run", json=payload).json()
        second = client.post("/api/v1/backtest/run", json=payload).json()

    assert first == second