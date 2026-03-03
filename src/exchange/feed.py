import asyncio
import logging

from kraken.spot import SpotWSClient

logger = logging.getLogger(__name__)


class KrakenFeed(SpotWSClient):
    def __init__(self, message_queue: asyncio.Queue) -> None:
        super().__init__()
        self._queue = message_queue

    async def on_message(self, message: dict) -> None:
        channel = message.get("channel", "")
        if channel in ("heartbeat",) or message.get("method") == "pong":
            return
        if channel in ("ticker", "ohlc"):
            await self._queue.put(message)
        else:
            logger.debug("Unhandled WS channel: %s", channel)

    async def subscribe_ticker(self, pairs: list[str]) -> None:
        await self.subscribe(params={"channel": "ticker", "symbol": pairs})

    async def subscribe_ohlc(self, pairs: list[str], interval: int = 60) -> None:
        await self.subscribe(
            params={"channel": "ohlc", "symbol": pairs, "interval": interval}
        )
