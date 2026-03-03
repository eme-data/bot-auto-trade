import asyncio
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.core.bot import TradingBot
from src.dashboard.api import router as api_router
from src.dashboard.router import router as dash_router
from src.utils.config import load_config
from src.utils.logger import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    setup_logging()
    logger = get_logger("main")

    try:
        config = load_config()
    except KeyError as e:
        print(f"ERROR: Missing environment variable: {e}")
        print("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"ERROR: Config file not found: {e}")
        sys.exit(1)

    logger.info("Configuration loaded. dry_run=%s", config.bot.dry_run)
    if not config.bot.dry_run:
        logger.warning("*** LIVE TRADING MODE ***")

    bot = TradingBot(config)
    app.state.bot = bot
    app.state.config = config

    bot_task = asyncio.create_task(bot.run(), name="trading-bot")
    logger.info(
        "Dashboard: http://%s:%d", config.dashboard.host, config.dashboard.port
    )

    yield

    # --- SHUTDOWN ---
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass
    logger.info("Bot stopped.")


app = FastAPI(title="Kraken Trading Bot", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(dash_router)
app.include_router(api_router)


if __name__ == "__main__":
    setup_logging()
    try:
        config = load_config()
    except (KeyError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    uvicorn.run(
        "main:app",
        host=config.dashboard.host,
        port=config.dashboard.port,
        log_level="info",
    )
