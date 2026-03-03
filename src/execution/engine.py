import json
import logging
from datetime import datetime, timezone

from ..exchange.client import KrakenRESTClient
from ..risk.manager import RiskManager, RiskAssessment
from ..strategies.base import Signal, SignalAction
from ..utils.config import AppConfig
from ..utils.database import insert_trade

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(
        self,
        rest_client: KrakenRESTClient,
        risk_manager: RiskManager,
        config: AppConfig,
    ) -> None:
        self._client = rest_client
        self._risk = risk_manager
        self._config = config
        self._dry_run = config.bot.dry_run

    async def process_signal(
        self,
        signal: Signal,
        portfolio_total_usd: float,
        current_price: float,
    ) -> bool:
        if signal.action == SignalAction.HOLD:
            return False

        if self._risk.is_halted:
            logger.warning("Signal ignored — bot is halted.")
            return False

        side = signal.action.value
        assessment: RiskAssessment = self._risk.approve_order(
            side=side,
            portfolio_total_usd=portfolio_total_usd,
            current_price=current_price,
        )

        if not assessment.approved:
            logger.info(
                "Signal REJECTED: %s | Reason: %s", signal.pair, assessment.reason
            )
            return False

        order_type = "limit" if signal.suggested_price else "market"
        price = signal.suggested_price

        logger.info(
            "[%s] %s %s %s %.6f @ %s | Strategy: %s | Confidence: %.2f",
            "DRY-RUN" if self._dry_run else "LIVE",
            side.upper(),
            signal.pair,
            order_type,
            assessment.adjusted_volume,
            f"{price:.4f}" if price else "market",
            signal.strategy,
            signal.confidence,
        )

        if self._dry_run:
            result = await self._client.place_order(
                pair=signal.pair,
                side=side,
                order_type=order_type,
                volume=assessment.adjusted_volume,
                price=price,
                validate=True,
            )
            txid = f"DRYRUN_{datetime.now(timezone.utc).isoformat()}"
        else:
            result = await self._client.place_order(
                pair=signal.pair,
                side=side,
                order_type=order_type,
                volume=assessment.adjusted_volume,
                price=price,
                validate=False,
            )
            if not result:
                logger.error("Order placement failed for %s", signal.pair)
                return False
            txid = result.get("txid", ["unknown"])[0] if result.get("txid") else "unknown"

        await insert_trade(
            {
                "txid": txid,
                "pair": signal.pair,
                "side": side,
                "order_type": order_type,
                "price": price or current_price,
                "volume": assessment.adjusted_volume,
                "fee": None,
                "strategy": signal.strategy,
                "dry_run": 1 if self._dry_run else 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw_response": json.dumps(result) if result else None,
            }
        )

        if not self._dry_run and side == "buy":
            self._risk.register_position_opened()

        return True

    async def check_stop_losses(
        self,
        open_positions: list[dict],
        current_prices: dict[str, float],
        portfolio_total_usd: float,
    ) -> None:
        for position in open_positions:
            pair = position["pair"]
            entry_price = position["price"]
            current = current_prices.get(pair)
            if not current:
                continue

            stop_price = self._risk.calculate_stop_loss_price(entry_price, "buy")
            if current <= stop_price:
                logger.warning(
                    "STOP-LOSS triggered for %s: entry=%.4f stop=%.4f current=%.4f",
                    pair,
                    entry_price,
                    stop_price,
                    current,
                )
                stop_signal = Signal(
                    action=SignalAction.SELL,
                    pair=pair,
                    strategy="StopLoss",
                    confidence=1.0,
                    reason=f"Stop-loss at {current:.4f}",
                )
                await self.process_signal(stop_signal, portfolio_total_usd, current)
