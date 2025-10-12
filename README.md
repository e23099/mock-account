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

### Rebuilding balance / equity history

Version 2 keeps every trade, fee and realized PnL entry, so you can replay
events in chronological order and capture the account state at each step. The
snippet below illustrates how to regenerate an equity curve given historical
prices, FX rates and fills:

```python
from collections import defaultdict

events = defaultdict(list)
for price in historical_prices:  # each item -> {instrument, price, currency, timestamp}
    events[price["timestamp"]].append(("price", price))
for fx in historical_fx_rates:  # each item -> {from, to, rate, timestamp}
    events[fx["timestamp"]].append(("fx", fx))
for fill in historical_trades:  # each item -> {instrument, quantity, price, currency, timestamp, ...}
    events[fill["timestamp"]].append(("trade", fill))

snapshots = []
for timestamp in sorted(events):
    for kind, payload in events[timestamp]:
        if kind == "price":
            account.update_price(**payload)
        elif kind == "fx":
            account.update_fx_rate(**payload)
        elif kind == "trade":
            account.record_trade(**payload)
    state = account.get_account_state()
    snapshots.append({"timestamp": timestamp, **state})

# snapshots now contains balance/equity/unrealized history in base currency
```

By storing each snapshot (for example, in a DataFrame) you can reconstruct the
entire account balance and equity history for analytics or visualization.

## Testing

```bash
pytest
```
