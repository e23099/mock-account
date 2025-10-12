import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from mock_account import FlatFeeModel, MockAccount


def test_basic_long_position():
    account = MockAccount(base_currency="USD")
    account.update_price("AAPL", price=100.0, currency="USD", timestamp=1)

    account.record_trade(
        "AAPL",
        quantity=10,
        price=100.0,
        currency="USD",
        timestamp=1,
    )

    account.update_price("AAPL", price=110.0, currency="USD", timestamp=2)

    state = account.get_account_state()
    assert state["balance"] == pytest.approx(-1000.0)
    assert state["unrealized_pnl"] == pytest.approx(100.0)
    assert state["equity"] == pytest.approx(100.0)

    positions = account.get_positions()
    assert positions["AAPL"]["net_quantity"] == pytest.approx(10.0)


def test_fifo_and_realized_pnl():
    account = MockAccount(base_currency="USD")
    account.update_price("AAPL", price=100.0, currency="USD", timestamp=1)
    account.record_trade("AAPL", quantity=5, price=100.0, currency="USD", timestamp=1)
    account.record_trade("AAPL", quantity=5, price=105.0, currency="USD", timestamp=2)

    account.update_price("AAPL", price=120.0, currency="USD", timestamp=3)
    account.record_trade("AAPL", quantity=-6, price=120.0, currency="USD", timestamp=3)

    realized = account.get_realized_pnl_history()
    assert len(realized) == 2
    assert realized[0].quantity == pytest.approx(5.0)
    assert realized[0].amount == pytest.approx(100.0)
    assert realized[0].direction == "long"
    assert realized[0].open_timestamp == 1
    assert realized[1].quantity == pytest.approx(1.0)
    assert realized[1].amount == pytest.approx(15.0)
    assert realized[1].open_timestamp == 2

    positions = account.get_positions()
    assert positions["AAPL"]["net_quantity"] == pytest.approx(4.0)
    assert positions["AAPL"]["average_price"] == pytest.approx(105.0)


def test_fx_and_short_position():
    account = MockAccount(base_currency="USD")
    account.update_fx_rate("HKD", "USD", rate=0.128, timestamp=1)
    account.update_price("0700.HK", price=300.0, currency="HKD", timestamp=1)

    account.record_trade("0700.HK", quantity=100, price=300.0, currency="HKD", timestamp=1)
    account.update_price("0700.HK", price=320.0, currency="HKD", timestamp=2)

    state = account.get_account_state()
    assert state["balance"] == pytest.approx(-30000.0 * 0.128)
    assert state["unrealized_pnl"] == pytest.approx(2000.0 * 0.128)
    assert state["equity"] == pytest.approx((-30000.0 + 32000.0) * 0.128)

    # Close the position to realize PnL and ensure FX conversion works.
    account.record_trade("0700.HK", quantity=-100, price=325.0, currency="HKD", timestamp=3)
    realized = account.get_realized_pnl_history()[-1]
    assert realized.amount == pytest.approx((325.0 - 300.0) * 100)
    assert realized.base_amount == pytest.approx((325.0 - 300.0) * 100 * 0.128)
    assert realized.fx_rate == pytest.approx(0.128)


def test_fee_application():
    account = MockAccount(base_currency="USD", fee_models=[FlatFeeModel(amount=2.0, currency="USD")])
    account.update_price("MSFT", price=250.0, currency="USD", timestamp=1)
    account.record_trade("MSFT", quantity=1, price=250.0, currency="USD", timestamp=1)

    fees = account.get_fee_history()
    assert len(fees) == 1
    assert fees[0].amount == pytest.approx(2.0)
    assert account.get_cash_balances()["USD"] == pytest.approx(-252.0)


def test_short_position_realized_direction():
    account = MockAccount(base_currency="USD")
    account.update_price("ES", price=4000.0, currency="USD", timestamp=1)

    account.record_trade(
        "ES",
        quantity=-2,
        price=4000.0,
        currency="USD",
        timestamp=1,
        multiplier=50,
    )

    positions = account.get_positions()
    assert positions["ES"]["net_quantity"] == pytest.approx(-2.0)
    assert positions["ES"]["average_price"] == pytest.approx(4000.0)

    account.update_price("ES", price=3900.0, currency="USD", timestamp=2)
    state = account.get_account_state()
    assert state["unrealized_pnl"] == pytest.approx(10000.0)
    assert state["equity"] == pytest.approx(10000.0)

    account.record_trade(
        "ES",
        quantity=2,
        price=3900.0,
        currency="USD",
        timestamp=3,
        multiplier=50,
    )
    realized = account.get_realized_pnl_history()[-1]
    assert realized.direction == "short"
    assert realized.amount == pytest.approx(10000.0)
    assert realized.quantity == pytest.approx(2.0)
