import logging

import pandas as pd

from ..utils.config import GridConfig
from .base import BaseStrategy, Signal, SignalAction

logger = logging.getLogger(__name__)


class GridStrategy(BaseStrategy):
    def __init__(self, config: GridConfig) -> None:
        super().__init__(config)
        self._grids: dict[str, list[float]] = {}
        self._active_buys: dict[str, set[float]] = {}
        self._active_sells: dict[str, set[float]] = {}

    def _build_grid(self, pair: str, center_price: float) -> list[float]:
        cfg: GridConfig = self.config
        half = cfg.grid_levels // 2
        levels = [
            round(center_price * (1 + i * cfg.grid_spacing_pct), 8)
            for i in range(-half, half + 1)
        ]
        self._grids[pair] = levels
        self._active_buys[pair] = set()
        self._active_sells[pair] = set()
        logger.info(
            "Grid built for %s: %d levels around %.2f", pair, len(levels), center_price
        )
        return levels

    def evaluate(self, df: pd.DataFrame, pair: str, current_price: float) -> Signal:
        cfg: GridConfig = self.config
        if pair not in cfg.enabled_pairs:
            return self._hold(pair, "Pair not in grid config")

        if pair not in self._grids:
            self._build_grid(pair, current_price)

        levels = self._grids[pair]
        active_buys = self._active_buys[pair]
        active_sells = self._active_sells[pair]
        tolerance = current_price * cfg.grid_spacing_pct * 0.5

        # Check buy levels (below current price)
        buy_levels = [l for l in levels if l < current_price and l not in active_buys]
        if buy_levels:
            target = max(buy_levels)
            if abs(current_price - target) <= tolerance:
                active_buys.add(target)
                return Signal(
                    action=SignalAction.BUY,
                    pair=pair,
                    strategy="GridStrategy",
                    confidence=1.0,
                    suggested_price=target,
                    reason=f"Grid buy at level {target:.4f}",
                )

        # Check sell levels (above current price)
        sell_levels = [l for l in levels if l > current_price and l not in active_sells]
        if sell_levels:
            target = min(sell_levels)
            if abs(current_price - target) <= tolerance:
                active_sells.add(target)
                return Signal(
                    action=SignalAction.SELL,
                    pair=pair,
                    strategy="GridStrategy",
                    confidence=1.0,
                    suggested_price=target,
                    reason=f"Grid sell at level {target:.4f}",
                )

        return self._hold(pair, "No grid level triggered")

    def on_order_filled(self, pair: str, side: str, price: float) -> None:
        if side == "buy" and pair in self._active_buys:
            self._active_buys[pair].discard(price)
        elif side == "sell" and pair in self._active_sells:
            self._active_sells[pair].discard(price)
