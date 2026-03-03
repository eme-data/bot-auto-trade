import asyncio
import logging

import aiosqlite
from fastapi import APIRouter, Depends, Request

from ..utils.database import DB_PATH
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


def _get_bot(request: Request):
    return request.app.state.bot


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/status")
async def get_status(request: Request, _user: str = Depends(get_current_user)):
    bot = _get_bot(request)
    return {
        "running": bot.running,
        "dry_run": bot.config.bot.dry_run,
        "halted": bot._risk.is_halted,
        "strategies": [s.__class__.__name__ for s in bot._strategies],
        "trading_pairs": bot.config.bot.trading_pairs,
        "poll_interval": bot.config.bot.poll_interval_seconds,
    }


@router.get("/portfolio")
async def get_portfolio(request: Request, _user: str = Depends(get_current_user)):
    bot = _get_bot(request)
    return {
        "total_usd": bot._portfolio.total_usd,
        "balances": bot._portfolio.balances,
        "drawdown": bot._risk.get_drawdown(bot._portfolio.total_usd),
        "peak": bot._risk._peak_portfolio_value,
    }


@router.get("/portfolio/history")
async def get_portfolio_history(
    limit: int = 200, _user: str = Depends(get_current_user)
):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT timestamp, total_usd, drawdown FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in reversed(rows)]


@router.get("/trades")
async def get_trades(
    limit: int = 50,
    offset: int = 0,
    pair: str | None = None,
    strategy: str | None = None,
    _user: str = Depends(get_current_user),
):
    query = "SELECT * FROM trades"
    params: list = []
    conditions = []

    if pair:
        conditions.append("pair = ?")
        params.append(pair)
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()

    # Get total count
    count_query = "SELECT COUNT(*) FROM trades"
    if conditions:
        count_query += " WHERE " + " AND ".join(conditions)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            count_query, params[:-2] if conditions else []
        ) as cur:
            total = (await cur.fetchone())[0]

    return {"trades": [dict(r) for r in rows], "total": total}


@router.get("/ohlcv/{pair}")
async def get_ohlcv(
    pair: str, request: Request, _user: str = Depends(get_current_user)
):
    bot = _get_bot(request)
    df = bot._ohlcv_cache.get(pair)
    if df is None:
        return {"error": f"No data for {pair}", "data": []}

    # Return last 100 candles as JSON
    recent = df.tail(100).reset_index()
    recent["timestamp"] = recent["timestamp"].astype(str)
    return {"pair": pair, "data": recent.to_dict(orient="records")}


@router.post("/bot/pause")
async def pause_bot(request: Request, _user: str = Depends(get_current_user)):
    bot = _get_bot(request)
    bot.pause()
    logger.info("Bot paused via dashboard")
    return {"status": "paused"}


@router.post("/bot/resume")
async def resume_bot(request: Request, _user: str = Depends(get_current_user)):
    bot = _get_bot(request)
    bot.resume()
    logger.info("Bot resumed via dashboard")
    return {"status": "running"}


@router.post("/risk/resume")
async def resume_risk(request: Request, _user: str = Depends(get_current_user)):
    bot = _get_bot(request)
    bot._risk.resume()
    logger.info("Risk halt cleared via dashboard")
    return {"status": "risk resumed"}
