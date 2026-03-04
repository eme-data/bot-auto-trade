import logging

import aiosqlite
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..utils.config import load_config, save_env, save_settings
from ..utils.database import DB_PATH
from .auth import (
    create_token,
    get_current_user,
    get_current_user_or_redirect,
    verify_credentials,
)

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

router = APIRouter(tags=["dashboard"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not verify_credentials(username, password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Identifiants invalides"},
            status_code=401,
        )
    token = create_token(username)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=43200,  # 12h
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    bot = request.app.state.bot
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "portfolio_usd": bot._portfolio.total_usd if bot._portfolio else 0.0,
            "balances": bot._portfolio.balances if bot._portfolio else {},
            "dry_run": bot.config.bot.dry_run,
            "running": bot.running,
            "idle": bot.idle,
            "halted": bot._risk.is_halted,
            "strategies": [s.__class__.__name__ for s in bot._strategies],
            "pairs": bot.config.bot.trading_pairs,
            "drawdown": bot._risk.get_drawdown(bot._portfolio.total_usd if bot._portfolio else 0.0),
        },
    )


@router.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 100"
        ) as cur:
            trades = [dict(r) for r in await cur.fetchall()]

    return templates.TemplateResponse(
        request=request,
        name="trades.html",
        context={"user": user, "trades": trades},
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    bot = request.app.state.bot
    config = request.app.state.config
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
            "api_configured": config.api_configured,
            "api_key_masked": config.api_key[:4] + "****" if config.api_key else "",
            "bot_config": config.bot,
            "risk_config": config.risk,
            "strategies_config": config.strategies,
            "idle": bot.idle,
        },
    )


@router.post("/admin/keys")
async def save_api_keys(
    request: Request,
    api_key: str = Form(...),
    api_secret: str = Form(...),
):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    save_env({"KRAKEN_API_KEY": api_key, "KRAKEN_API_SECRET": api_secret})

    # Reload config and reconfigure bot
    config = load_config()
    request.app.state.config = config
    request.app.state.bot.reconfigure(config)

    logger.info("API keys updated via admin panel")
    return RedirectResponse(url="/admin?saved=keys", status_code=302)


@router.post("/admin/settings")
async def save_admin_settings(
    request: Request,
    dry_run: str = Form(""),
    trading_pairs: str = Form(...),
    poll_interval: int = Form(60),
    max_position_pct: float = Form(5.0),
    stop_loss_pct: float = Form(3.0),
    max_drawdown_pct: float = Form(15.0),
    max_open_positions: int = Form(3),
    active_strategy: str = Form("technical"),
):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    pairs = [p.strip() for p in trading_pairs.split(",") if p.strip()]

    save_settings({
        "bot": {
            "dry_run": dry_run == "on",
            "trading_pairs": pairs,
            "poll_interval_seconds": poll_interval,
        },
        "risk": {
            "max_position_pct": max_position_pct,
            "stop_loss_pct": stop_loss_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "max_open_positions": max_open_positions,
        },
        "strategies": {
            "active": active_strategy,
        },
    })

    # Reload config
    config = load_config()
    request.app.state.config = config
    request.app.state.bot.reconfigure(config)

    logger.info("Settings updated via admin panel")
    return RedirectResponse(url="/admin?saved=settings", status_code=302)


# --- HTMX Partials ---


@router.get("/partials/portfolio", response_class=HTMLResponse)
async def partial_portfolio(request: Request):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return HTMLResponse(status_code=401)

    bot = request.app.state.bot
    return templates.TemplateResponse(
        request=request,
        name="partials/portfolio.html",
        context={
            "portfolio_usd": bot._portfolio.total_usd if bot._portfolio else 0.0,
            "balances": bot._portfolio.balances if bot._portfolio else {},
            "drawdown": bot._risk.get_drawdown(bot._portfolio.total_usd if bot._portfolio else 0.0),
        },
    )


@router.get("/partials/status", response_class=HTMLResponse)
async def partial_status(request: Request):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return HTMLResponse(status_code=401)

    bot = request.app.state.bot
    return templates.TemplateResponse(
        request=request,
        name="partials/bot_status.html",
        context={
            "running": bot.running,
            "idle": bot.idle,
            "dry_run": bot.config.bot.dry_run,
            "halted": bot._risk.is_halted,
            "strategies": [s.__class__.__name__ for s in bot._strategies],
            "pairs": bot.config.bot.trading_pairs,
        },
    )


@router.get("/partials/trades", response_class=HTMLResponse)
async def partial_trades(request: Request):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return HTMLResponse(status_code=401)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10"
        ) as cur:
            trades = [dict(r) for r in await cur.fetchall()]

    return templates.TemplateResponse(
        request=request,
        name="partials/trades_table.html",
        context={"trades": trades},
    )


@router.get("/partials/signals", response_class=HTMLResponse)
async def partial_signals(request: Request):
    user = get_current_user_or_redirect(request, request.cookies.get("access_token"))
    if not user:
        return HTMLResponse(status_code=401)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 5"
        ) as cur:
            signals = [dict(r) for r in await cur.fetchall()]

    return templates.TemplateResponse(
        request=request,
        name="partials/signals.html",
        context={"signals": signals},
    )
