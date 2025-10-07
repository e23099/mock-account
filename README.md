# Mock Account

A lightweight Python toolkit for simulating a multi-asset, multi-currency brokerage account. It keeps track of cash balances, FIFO-based positions, realized and unrealized PnL and supports pluggable fee models.

## Features

- Multiple assets with independent price streams.
- Multi-currency cash management with FX conversion to a configurable base currency.
- FIFO accounting for positions and realized PnL history with FX references.
- Pluggable fee models (flat or notional) with support for rebates.
- Snapshot utilities for balance, equity and unrealized PnL.
- Comprehensive transaction, fee and realized PnL history retrieval.

## Installation

The project is a plain Python package. Add the repository root to your `PYTHONPATH` or install it in editable mode:

```bash
pip install -e .
```

## Usage

```python
from mock_account import MockAccount, FlatFeeModel

account = MockAccount(
    base_currency="USD",
    initial_balances={"USD": 10_000.0},
    fee_models=[FlatFeeModel(amount=1.5, currency="USD")],
)

account.update_fx_rate("HKD", "USD", rate=0.128, timestamp=1700000000)
account.update_price("0700.HK", price=300.0, currency="HKD", timestamp=1700000000)
account.record_trade("0700.HK", quantity=100, price=300.0, currency="HKD", timestamp=1700000000)
account.update_price("0700.HK", price=320.0, currency="HKD", timestamp=1700003600)

state = account.get_account_state()
print(state["equity"], state["unrealized_pnl"])

for instrument, position in account.get_positions().items():
    print(instrument, position)
```

## Testing

```bash
pytest
```
