from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd


class SignalAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    action: SignalAction
    pair: str
    strategy: str
    confidence: float
    suggested_price: float | None = None
    reason: str = ""


class BaseStrategy(ABC):
    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    def evaluate(self, df: pd.DataFrame, pair: str, current_price: float) -> Signal: ...

    def _hold(self, pair: str, reason: str = "") -> Signal:
        return Signal(
            action=SignalAction.HOLD,
            pair=pair,
            strategy=self.__class__.__name__,
            confidence=0.0,
            reason=reason,
        )
