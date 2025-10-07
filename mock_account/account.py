"""Core account model for the mock trading environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, MutableMapping, Optional, Tuple

from .fees import Fee, FeeModel, apply_fee_models


@dataclass
class PriceRecord:
    price: float
    currency: str
    timestamp: int
    metadata: Optional[Dict[str, object]] = None


@dataclass
class FxRate:
    rate: float
    timestamp: int


@dataclass
class PositionLot:
    quantity: float
    price: float
    currency: str
    timestamp: int


@dataclass
class RealizedPnL:
    instrument: str
    quantity: float
    direction: str
    amount: float
    currency: str
    base_amount: float
    base_currency: str
    fx_rate: float
    timestamp: int
    open_timestamp: int


class MockAccount:
    """Maintain multi-asset, multi-currency trading balances using FIFO.

    Parameters
    ----------
    base_currency:
        All reported balances are expressed in this currency. FX rates must be
        supplied so that amounts can be converted into ``base_currency``.
    initial_balances:
        Optional mapping from currency to opening cash balance. Currencies that
        are not present start at zero.
    fee_models:
        Optional iterable of :class:`FeeModel` instances used to calculate trade
        fees. Multiple models can be supplied and will be evaluated in order.
    """

    def __init__(
        self,
        *,
        base_currency: str,
        initial_balances: Optional[MutableMapping[str, float]] = None,
        fee_models: Optional[Iterable[FeeModel]] = None,
    ) -> None:
        self.base_currency = base_currency
        self.cash_balances: Dict[str, float] = {
            currency: float(amount) for currency, amount in (initial_balances or {}).items()
        }
        self.positions: Dict[str, List[PositionLot]] = {}
        self.prices: Dict[str, PriceRecord] = {}
        self.fx_rates: Dict[Tuple[str, str], FxRate] = {}
        self.trade_history: List[Dict[str, object]] = []
        self.fee_history: List[Fee] = []
        self.realized_pnl_history: List[RealizedPnL] = []
        self.fee_models: List[FeeModel] = list(fee_models or [])

    # ------------------------------------------------------------------
    # Data ingestion utilities
    # ------------------------------------------------------------------
    def update_price(
        self,
        instrument: str,
        *,
        price: float,
        currency: str,
        timestamp: int,
        metadata: Optional[Dict[str, object]] = None,
    ) -> None:
        """Update the latest price for ``instrument``."""

        self.prices[instrument] = PriceRecord(
            price=float(price),
            currency=currency,
            timestamp=int(timestamp),
            metadata=metadata,
        )

    def update_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        *,
        rate: float,
        timestamp: int,
    ) -> None:
        """Register an FX rate that converts ``from_currency`` into ``to_currency``."""

        fx = FxRate(rate=float(rate), timestamp=int(timestamp))
        self.fx_rates[(from_currency, to_currency)] = fx
        if rate != 0:
            self.fx_rates[(to_currency, from_currency)] = FxRate(rate=1.0 / float(rate), timestamp=int(timestamp))

    def record_trade(
        self,
        instrument: str,
        *,
        quantity: float,
        price: float,
        currency: str,
        timestamp: int,
        multiplier: float = 1.0,
        metadata: Optional[Dict[str, object]] = None,
    ) -> None:
        """Record a trade for ``instrument`` and update cash, positions and fees."""

        trade = {
            "instrument": instrument,
            "quantity": float(quantity),
            "price": float(price),
            "currency": currency,
            "timestamp": int(timestamp),
            "multiplier": float(multiplier),
        }
        if metadata is not None:
            trade["metadata"] = metadata

        if trade["quantity"] == 0:
            raise ValueError("quantity must be non-zero")

        self._apply_cash_flow(currency=currency, amount=-trade["quantity"] * trade["price"] * trade["multiplier"])
        fees = apply_fee_models(self.fee_models, trade)
        for fee in fees:
            self._apply_cash_flow(currency=fee.currency, amount=-fee.amount)
        self.fee_history.extend(fees)
        self.trade_history.append(trade)

        realized = self._update_positions(trade)
        self.realized_pnl_history.extend(realized)

    # ------------------------------------------------------------------
    # Reporting utilities
    # ------------------------------------------------------------------
    def get_account_state(self) -> Dict[str, float]:
        """Return balance, equity and unrealized PnL expressed in base currency."""

        cash_base = self._cash_in_base()
        positions_value, unrealized = self._positions_valuation()
        equity = cash_base + positions_value
        return {
            "balance": cash_base,
            "equity": equity,
            "unrealized_pnl": unrealized,
        }

    def get_trade_history(self) -> List[Dict[str, object]]:
        return list(self.trade_history)

    def get_fee_history(self) -> List[Fee]:
        return list(self.fee_history)

    def get_realized_pnl_history(self) -> List[RealizedPnL]:
        return list(self.realized_pnl_history)

    def get_cash_balances(self) -> Dict[str, float]:
        """Return a copy of current cash balances by currency."""

        return dict(self.cash_balances)

    def get_positions(self) -> Dict[str, Dict[str, float]]:
        """Return the current open positions keyed by instrument."""

        summary: Dict[str, Dict[str, float]] = {}
        for instrument, lots in self.positions.items():
            if not lots:
                continue
            net_quantity = sum(lot.quantity for lot in lots)
            if abs(net_quantity) < 1e-12:
                continue
            cost = sum(lot.price * lot.quantity for lot in lots)
            currency = lots[0].currency
            average_price = cost / net_quantity
            summary[instrument] = {
                "net_quantity": net_quantity,
                "average_price": average_price,
                "currency": currency,
            }
        return summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_cash_flow(self, *, currency: str, amount: float) -> None:
        self.cash_balances[currency] = self.cash_balances.get(currency, 0.0) + float(amount)

    def _cash_in_base(self) -> float:
        total = 0.0
        for currency, amount in self.cash_balances.items():
            total += self._convert(amount, currency, self.base_currency)
        return total

    def _positions_valuation(self) -> Tuple[float, float]:
        market_value = 0.0
        unrealized = 0.0
        for instrument, lots in self.positions.items():
            if not lots:
                continue
            price = self.prices.get(instrument)
            if price is None:
                raise ValueError(f"Missing price for {instrument}")
            for lot in lots:
                if lot.currency != price.currency:
                    raise ValueError(
                        f"Currency mismatch for {instrument}: lot {lot.currency} vs price {price.currency}"
                    )
            net_qty = sum(lot.quantity for lot in lots)
            market_value += self._convert(price.price * net_qty, price.currency, self.base_currency)
            for lot in lots:
                lot_pnl = (price.price - lot.price) * lot.quantity
                unrealized += self._convert(lot_pnl, lot.currency, self.base_currency)
        return market_value, unrealized

    def _convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        if from_currency == to_currency:
            return float(amount)
        key = (from_currency, to_currency)
        if key not in self.fx_rates:
            raise ValueError(f"Missing FX rate for {from_currency}->{to_currency}")
        rate = self.fx_rates[key]
        return float(amount) * rate.rate

    def _update_positions(self, trade: Dict[str, object]) -> List[RealizedPnL]:
        instrument = str(trade["instrument"])
        quantity = float(trade["quantity"]) * float(trade["multiplier"])
        price = float(trade["price"])
        currency = str(trade["currency"])
        timestamp = int(trade["timestamp"])

        lots = self.positions.setdefault(instrument, [])
        realized: List[RealizedPnL] = []

        qty_to_process = quantity
        idx = 0
        while idx < len(lots) and qty_to_process != 0:
            lot = lots[idx]
            if (lot.quantity > 0) == (qty_to_process > 0):
                break
            match_qty = min(abs(qty_to_process), abs(lot.quantity))
            direction = 1.0 if lot.quantity > 0 else -1.0
            pnl_amount = (price - lot.price) * match_qty * direction
            fx_rate = self._fx_rate_for(currency)
            realized.append(
                RealizedPnL(
                    instrument=instrument,
                    quantity=match_qty,
                    direction="long" if direction > 0 else "short",
                    amount=pnl_amount,
                    currency=currency,
                    base_amount=pnl_amount * fx_rate,
                    base_currency=self.base_currency,
                    fx_rate=fx_rate,
                    timestamp=timestamp,
                    open_timestamp=lot.timestamp,
                )
            )

            lot.quantity -= direction * match_qty
            qty_to_process += direction * match_qty
            if abs(lot.quantity) < 1e-12:
                lots.pop(idx)
            else:
                idx += 1

        if abs(qty_to_process) > 1e-12:
            lots.append(
                PositionLot(
                    quantity=qty_to_process,
                    price=price,
                    currency=currency,
                    timestamp=timestamp,
                )
            )

        return realized

    def _fx_rate_for(self, currency: str) -> float:
        if currency == self.base_currency:
            return 1.0
        key = (currency, self.base_currency)
        if key not in self.fx_rates:
            raise ValueError(f"Missing FX rate for {currency}->{self.base_currency}")
        return self.fx_rates[key].rate
