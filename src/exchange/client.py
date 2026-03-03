import logging
from typing import Any

from kraken.spot import SpotAsyncClient

logger = logging.getLogger(__name__)

# Kraken uses internal names like XXBTZUSD; map to readable forms
PAIR_ALIASES = {
    "XXBTZUSD": "XBT/USD",
    "XETHZUSD": "ETH/USD",
    "XXBTZEUR": "XBT/EUR",
    "XETHZEUR": "ETH/EUR",
}


class KrakenRESTClient:
    def __init__(self, api_key: str, api_secret: str) -> None:
        self._key = api_key
        self._secret = api_secret

    async def get_balance(self) -> dict[str, float] | None:
        try:
            async with SpotAsyncClient(key=self._key, secret=self._secret) as client:
                resp = await client.request("POST", "/0/private/Balance")
            if resp.get("error"):
                logger.error("Balance error: %s", resp["error"])
                return None
            return {k: float(v) for k, v in resp.get("result", {}).items()}
        except Exception as e:
            logger.exception("Exception fetching balance: %s", e)
            return None

    async def get_ticker(self, pairs: list[str]) -> dict | None:
        pair_str = ",".join(pairs)
        try:
            async with SpotAsyncClient() as client:
                resp = await client.request(
                    "GET", "/0/public/Ticker", params={"pair": pair_str}
                )
            if resp.get("error"):
                logger.error("Ticker error: %s", resp["error"])
                return None
            return resp.get("result")
        except Exception as e:
            logger.exception("Exception fetching ticker: %s", e)
            return None

    async def get_ohlcv(
        self, pair: str, interval: int, since: int | None = None
    ) -> list | None:
        params: dict[str, Any] = {"pair": pair, "interval": interval}
        if since:
            params["since"] = since
        try:
            async with SpotAsyncClient() as client:
                resp = await client.request(
                    "GET", "/0/public/OHLC", params=params
                )
            if resp.get("error"):
                logger.error("OHLC error: %s", resp["error"])
                return None
            result = resp.get("result", {})
            data_key = next((k for k in result if k != "last"), None)
            return result.get(data_key) if data_key else None
        except Exception as e:
            logger.exception("Exception fetching OHLCV: %s", e)
            return None

    async def get_asset_pairs(self) -> dict | None:
        try:
            async with SpotAsyncClient() as client:
                resp = await client.request("GET", "/0/public/AssetPairs")
            if resp.get("error"):
                logger.error("AssetPairs error: %s", resp["error"])
                return None
            return resp.get("result")
        except Exception as e:
            logger.exception("Exception fetching asset pairs: %s", e)
            return None

    async def place_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        volume: float,
        price: float | None = None,
        validate: bool = False,
    ) -> dict | None:
        params: dict[str, Any] = {
            "pair": pair,
            "type": side,
            "ordertype": order_type,
            "volume": str(volume),
            "validate": validate,
        }
        if price is not None and order_type == "limit":
            params["price"] = str(price)
        try:
            async with SpotAsyncClient(key=self._key, secret=self._secret) as client:
                resp = await client.request(
                    "POST", "/0/private/AddOrder", params=params
                )
            if resp.get("error"):
                logger.error("AddOrder error: %s | params: %s", resp["error"], params)
                return None
            return resp.get("result")
        except Exception as e:
            logger.exception("Exception placing order: %s", e)
            return None

    async def cancel_order(self, txid: str) -> bool:
        try:
            async with SpotAsyncClient(key=self._key, secret=self._secret) as client:
                resp = await client.request(
                    "POST", "/0/private/CancelOrder", params={"txid": txid}
                )
            if resp.get("error"):
                logger.error("CancelOrder error: %s", resp["error"])
                return False
            return True
        except Exception as e:
            logger.exception("Exception canceling order %s: %s", txid, e)
            return False

    async def get_open_orders(self) -> dict | None:
        try:
            async with SpotAsyncClient(key=self._key, secret=self._secret) as client:
                resp = await client.request("POST", "/0/private/OpenOrders")
            if resp.get("error"):
                logger.error("OpenOrders error: %s", resp["error"])
                return None
            return resp.get("result", {}).get("open")
        except Exception as e:
            logger.exception("Exception fetching open orders: %s", e)
            return None
