import logging
from dataclasses import dataclass

from ..utils.config import RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskAssessment:
    approved: bool
    adjusted_volume: float
    reason: str


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self._halted = False
        self._open_position_count = 0
        self._peak_portfolio_value: float | None = None

    @property
    def is_halted(self) -> bool:
        return self._halted

    def check_drawdown(self, current_total_usd: float) -> bool:
        if self._peak_portfolio_value is None:
            self._peak_portfolio_value = current_total_usd
            return True

        if current_total_usd > self._peak_portfolio_value:
            self._peak_portfolio_value = current_total_usd

        drawdown = (
            (self._peak_portfolio_value - current_total_usd)
            / self._peak_portfolio_value
        )

        if drawdown >= self.config.max_drawdown_pct:
            if not self._halted:
                logger.critical(
                    "MAX DRAWDOWN BREACHED: %.2f%% (peak=%.2f, current=%.2f). BOT HALTED.",
                    drawdown * 100,
                    self._peak_portfolio_value,
                    current_total_usd,
                )
                self._halted = True
        return not self._halted

    def get_drawdown(self, current_total_usd: float) -> float:
        if self._peak_portfolio_value is None or self._peak_portfolio_value == 0:
            return 0.0
        return (
            (self._peak_portfolio_value - current_total_usd)
            / self._peak_portfolio_value
        )

    def approve_order(
        self,
        side: str,
        portfolio_total_usd: float,
        current_price: float,
        requested_volume: float | None = None,
    ) -> RiskAssessment:
        if self._halted:
            return RiskAssessment(False, 0.0, "Bot is halted due to max drawdown")

        if side == "buy" and self._open_position_count >= self.config.max_open_positions:
            return RiskAssessment(
                False,
                0.0,
                f"Max open positions reached ({self.config.max_open_positions})",
            )

        max_usd = portfolio_total_usd * self.config.max_position_pct
        max_volume = max_usd / current_price if current_price > 0 else 0.0

        safe_volume = min(requested_volume, max_volume) if requested_volume else max_volume

        if safe_volume <= 0:
            return RiskAssessment(False, 0.0, "Calculated volume is zero or negative")

        return RiskAssessment(True, safe_volume, "Approved")

    def calculate_stop_loss_price(self, entry_price: float, side: str) -> float:
        if side == "buy":
            return entry_price * (1 - self.config.stop_loss_pct)
        return entry_price * (1 + self.config.stop_loss_pct)

    def register_position_opened(self) -> None:
        self._open_position_count += 1

    def register_position_closed(self) -> None:
        self._open_position_count = max(0, self._open_position_count - 1)

    def resume(self) -> None:
        logger.warning("Risk halt manually cleared. Trading resuming.")
        self._halted = False
