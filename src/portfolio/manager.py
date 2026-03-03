import logging
from datetime import datetime, timezone

from ..exchange.client import KrakenRESTClient
from ..utils.database import save_portfolio_snapshot

logger = logging.getLogger(__name__)


class PortfolioManager:
    def __init__(self, rest_client: KrakenRESTClient) -> None:
        self._client = rest_client
        self._balances: dict[str, float] = {}
        self._total_usd: float = 0.0

    @property
    def total_usd(self) -> float:
        return self._total_usd

    @property
    def balances(self) -> dict[str, float]:
        return self._balances

    async def refresh(self, current_prices: dict[str, float]) -> float:
        raw_balances = await self._client.get_balance()
        if not raw_balances:
            logger.warning("Failed to fetch balances from Kraken")
            return self._total_usd

        self._balances = {k: v for k, v in raw_balances.items() if v > 0}

        # Start with USD balance (Kraken uses ZUSD)
        total = self._balances.get("ZUSD", 0.0)

        for asset, amount in self._balances.items():
            if asset in ("ZUSD", "USD") or amount == 0:
                continue
            # Try common pair formats to find a matching price
            clean = asset.lstrip("XZ")
            for pair_key, price in current_prices.items():
                if clean in pair_key:
                    total += amount * price
                    break

        self._total_usd = total
        logger.debug("Portfolio: %.2f USD | %s", total, self._balances)
        return total

    async def save_snapshot(self, drawdown: float) -> None:
        await save_portfolio_snapshot(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "balances": self._balances,
                "total_usd": self._total_usd,
                "drawdown": drawdown,
            }
        )
