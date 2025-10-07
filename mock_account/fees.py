"""Fee model abstractions used by the mock trading account."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class Fee:
    """Represents a fee charged on a trade.

    Attributes
    ----------
    name:
        Descriptive name for the fee (e.g. "commission", "rebate").
    amount:
        The monetary amount of the fee expressed in ``currency``. Fees that
        decrease cash balances should therefore use a positive ``amount`` while
        rebates should provide a negative amount.
    currency:
        Currency code for the fee amount.
    timestamp:
        Epoch timestamp when the fee is incurred.
    metadata:
        Optional dictionary for model specific details such as tier
        information.
    """

    name: str
    amount: float
    currency: str
    timestamp: int
    metadata: Dict[str, object] = field(default_factory=dict)


class FeeModel(ABC):
    """Base class for all fee models.

    Fee models receive the trade dictionary supplied to
    :meth:`mock_account.account.MockAccount.record_trade` and return the fees
    that should be charged for the trade. Custom models can subclass
    :class:`FeeModel` and implement :meth:`calculate`.
    """

    @abstractmethod
    def calculate(self, trade: Dict[str, object]) -> Sequence[Fee]:
        """Return the fees that should be charged for ``trade``."""


class FlatFeeModel(FeeModel):
    """Charges a constant fee for every trade."""

    def __init__(self, amount: float, currency: str, name: str = "flat_fee") -> None:
        self.amount = float(amount)
        self.currency = currency
        self.name = name

    def calculate(self, trade: Dict[str, object]) -> Sequence[Fee]:
        return [
            Fee(
                name=self.name,
                amount=self.amount,
                currency=self.currency,
                timestamp=int(trade["timestamp"]),
            )
        ]


class PerNotionalFeeModel(FeeModel):
    """Charges a fee proportional to trade notional.

    Parameters
    ----------
    rate:
        Fee rate expressed as a proportion of trade notional (e.g. ``0.0005``
        for 5 bps).
    minimum:
        Optional minimum fee amount. Defaults to ``0``.
    currency:
        Currency in which the fee is charged. When ``None`` the trade currency
        is used.
    name:
        Descriptive name for the fee.
    """

    def __init__(
        self,
        rate: float,
        *,
        minimum: float = 0.0,
        currency: str | None = None,
        name: str = "notional_fee",
    ) -> None:
        self.rate = float(rate)
        self.minimum = float(minimum)
        self.currency = currency
        self.name = name

    def calculate(self, trade: Dict[str, object]) -> Sequence[Fee]:
        notional = abs(float(trade["price"]) * float(trade["quantity"]) * float(trade.get("multiplier", 1.0)))
        amount = max(notional * self.rate, self.minimum)
        currency = self.currency or str(trade["currency"])
        return [
            Fee(
                name=self.name,
                amount=amount,
                currency=currency,
                timestamp=int(trade["timestamp"]),
            )
        ]


def apply_fee_models(fee_models: Iterable[FeeModel], trade: Dict[str, object]) -> List[Fee]:
    """Return the combined fees for ``trade`` from all ``fee_models``."""

    fees: List[Fee] = []
    for model in fee_models:
        fees.extend(model.calculate(trade))
    return fees
