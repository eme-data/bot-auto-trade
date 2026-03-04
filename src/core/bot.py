import asyncio
import logging

from ..analysis.indicators import compute_all_indicators
from ..analysis.ohlcv import kraken_ohlcv_to_dataframe
from ..exchange.client import KrakenRESTClient
from ..exchange.feed import KrakenFeed
from ..execution.engine import ExecutionEngine
from ..portfolio.manager import PortfolioManager
from ..risk.manager import RiskManager
from ..strategies.base import SignalAction
from ..strategies.grid import GridStrategy
from ..strategies.technical import TechnicalStrategy
from ..utils.config import AppConfig
from ..utils.database import init_db

logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._running = False
        self._paused = False
        self._idle = not config.api_configured
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

        if config.api_configured:
            self._rest = KrakenRESTClient(config.api_key, config.api_secret)
            self._feed = KrakenFeed(self._message_queue)
        else:
            self._rest = None
            self._feed = None

        self._risk = RiskManager(config.risk)
        self._execution = ExecutionEngine(self._rest, self._risk, config) if self._rest else None
        self._portfolio = PortfolioManager(self._rest) if self._rest else None

        active = config.strategies.active
        self._strategies = []
        if active in ("technical", "both"):
            self._strategies.append(TechnicalStrategy(config.strategies.technical))
        if active in ("grid", "both"):
            self._strategies.append(GridStrategy(config.strategies.grid))

        self._ohlcv_cache: dict = {}

    @property
    def running(self) -> bool:
        return self._running and not self._paused and not self._idle

    @property
    def idle(self) -> bool:
        return self._idle

    def pause(self) -> None:
        self._paused = True
        logger.info("Bot paused.")

    def resume(self) -> None:
        self._paused = False
        logger.info("Bot resumed.")

    def reconfigure(self, config: AppConfig) -> None:
        """Reconfigure the bot with new settings (e.g. after API keys are set)."""
        self.config = config
        if config.api_configured:
            self._rest = KrakenRESTClient(config.api_key, config.api_secret)
            self._feed = KrakenFeed(self._message_queue)
            self._execution = ExecutionEngine(self._rest, self._risk, config)
            self._portfolio = PortfolioManager(self._rest)
            self._idle = False
            logger.info("Bot reconfigured with API keys — ready to trade.")
        self._risk = RiskManager(config.risk)

    async def run(self) -> None:
        await init_db()

        if self._idle:
            logger.info("Bot started in idle mode — API keys not configured.")
            self._running = True
            try:
                while self._running:
                    if not self._idle:
                        break
                    await asyncio.sleep(2)
                if self._idle:
                    return
                # API keys were configured, start trading
                logger.info("Exiting idle mode, starting trading...")
            except asyncio.CancelledError:
                logger.info("Bot idle cancelled.")
                return

        logger.info(
            "Bot starting. dry_run=%s pairs=%s strategies=%s",
            self.config.bot.dry_run,
            self.config.bot.trading_pairs,
            [s.__class__.__name__ for s in self._strategies],
        )

        await self._bootstrap_ohlcv()

        self._running = True
        feed_task = asyncio.create_task(self._run_feed(), name="kraken-feed")
        queue_task = asyncio.create_task(self._process_feed_queue(), name="feed-queue")
        strategy_task = asyncio.create_task(self._strategy_loop(), name="strategy-loop")

        try:
            await asyncio.gather(feed_task, queue_task, strategy_task)
        except asyncio.CancelledError:
            logger.info("Bot tasks cancelled.")
        finally:
            await self._shutdown()

    async def _bootstrap_ohlcv(self) -> None:
        cfg = self.config.strategies.technical
        for pair in self.config.bot.trading_pairs:
            logger.info("Bootstrapping OHLCV for %s", pair)
            raw = await self._rest.get_ohlcv(pair, interval=cfg.timeframe)
            if raw:
                df = kraken_ohlcv_to_dataframe(raw)
                df = compute_all_indicators(df, **self._indicator_kwargs())
                self._ohlcv_cache[pair] = df
                logger.info("Loaded %d candles for %s", len(df), pair)
            else:
                logger.warning("No OHLCV data for %s", pair)
            await asyncio.sleep(0.5)  # respect rate limits

    def _indicator_kwargs(self) -> dict:
        cfg = self.config.strategies.technical
        return {
            "rsi_period": cfg.rsi_period,
            "macd_fast": cfg.macd_fast,
            "macd_slow": cfg.macd_slow,
            "macd_signal": cfg.macd_signal,
            "bb_period": cfg.bb_period,
            "bb_std": cfg.bb_std,
            "ma_fast": cfg.ma_fast,
            "ma_slow": cfg.ma_slow,
        }

    async def _run_feed(self) -> None:
        try:
            await self._feed.start()
            await self._feed.subscribe_ticker(self.config.bot.trading_pairs)
            if self.config.strategies.active in ("technical", "both"):
                await self._feed.subscribe_ohlc(
                    self.config.bot.trading_pairs,
                    interval=self.config.strategies.technical.timeframe,
                )
            while self._running and not self._feed.exception_occur:
                await asyncio.sleep(10)
            if self._feed.exception_occur:
                logger.error("WebSocket feed encountered an exception")
        except Exception as e:
            logger.exception("Feed error: %s", e)

    async def _process_feed_queue(self) -> None:
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(), timeout=5.0
                )
                channel = message.get("channel", "")
                if channel == "ohlc":
                    logger.debug("OHLC update: %s", message.get("data", [{}]))
                elif channel == "ticker":
                    logger.debug("Ticker update received")
            except asyncio.TimeoutError:
                continue

    async def _strategy_loop(self) -> None:
        # Wait a bit for initial data to arrive
        await asyncio.sleep(5)
        while self._running:
            if self._paused:
                await asyncio.sleep(1)
                continue
            try:
                await self._run_strategy_cycle()
            except Exception as e:
                logger.exception("Error in strategy cycle: %s", e)
            await asyncio.sleep(self.config.bot.poll_interval_seconds)

    async def _run_strategy_cycle(self) -> None:
        # 1. Fetch current prices
        ticker_data = await self._rest.get_ticker(self.config.bot.trading_pairs)
        if not ticker_data:
            logger.warning("No ticker data, skipping cycle")
            return

        current_prices: dict[str, float] = {}
        for pair_key, pair_data in ticker_data.items():
            try:
                current_prices[pair_key] = float(pair_data["c"][0])
            except (KeyError, IndexError, ValueError):
                pass

        # 2. Refresh portfolio and check drawdown
        total_usd = await self._portfolio.refresh(current_prices)
        if not self._risk.check_drawdown(total_usd):
            logger.critical("Trading halted — max drawdown breached.")
            return

        # 3. Refresh OHLCV data
        if self.config.strategies.active in ("technical", "both"):
            for pair in self.config.bot.trading_pairs:
                raw = await self._rest.get_ohlcv(
                    pair, interval=self.config.strategies.technical.timeframe
                )
                if raw:
                    df = kraken_ohlcv_to_dataframe(raw)
                    df = compute_all_indicators(df, **self._indicator_kwargs())
                    self._ohlcv_cache[pair] = df
                await asyncio.sleep(0.5)

        # 4. Evaluate strategies
        for pair in self.config.bot.trading_pairs:
            # Find price — Kraken may use different key format
            current_price = None
            for key, price in current_prices.items():
                clean_key = key.replace("X", "").replace("Z", "")
                clean_pair = pair.replace("/", "")
                if clean_pair in key or clean_pair in clean_key:
                    current_price = price
                    break

            if not current_price:
                logger.debug("No price found for %s", pair)
                continue

            for strategy in self._strategies:
                df = self._ohlcv_cache.get(pair)
                if df is None and not isinstance(strategy, GridStrategy):
                    continue

                signal = strategy.evaluate(
                    df if df is not None else __import__("pandas").DataFrame(),
                    pair,
                    current_price,
                )
                if signal.action != SignalAction.HOLD:
                    logger.info(
                        "Signal: %s %s | Confidence: %.2f | %s",
                        signal.action.value.upper(),
                        pair,
                        signal.confidence,
                        signal.reason,
                    )
                    await self._execution.process_signal(
                        signal, total_usd, current_price
                    )

        # 5. Save portfolio snapshot
        drawdown = self._risk.get_drawdown(total_usd)
        await self._portfolio.save_snapshot(drawdown)

    async def _shutdown(self) -> None:
        self._running = False
        if self._feed:
            try:
                await self._feed.close()
            except Exception:
                pass
        logger.info("Bot shut down cleanly.")
