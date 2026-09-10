from types import SimpleNamespace

from app.application.market_data.query_service import _instrument_exchange


def test_instrument_exchange_defaults_blank_to_nse():
    assert _instrument_exchange(SimpleNamespace(exchange=None)) == "NSE"
    assert _instrument_exchange(SimpleNamespace(exchange="")) == "NSE"
    assert _instrument_exchange(SimpleNamespace(exchange="  ")) == "NSE"


def test_instrument_exchange_preserves_value():
    assert _instrument_exchange(SimpleNamespace(exchange="NSE")) == "NSE"
    assert _instrument_exchange(SimpleNamespace(exchange=" BSE ")) == "BSE"
