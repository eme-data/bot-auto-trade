import logging

import aiosqlite
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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
            "portfolio_usd": bot._portfolio.total_usd,
            "balances": bot._portfolio.balances,
            "dry_run": bot.config.bot.dry_run,
            "running": bot.running,
            "halted": bot._risk.is_halted,
            "strategies": [s.__class__.__name__ for s in bot._strategies],
            "pairs": bot.config.bot.trading_pairs,
            "drawdown": bot._risk.get_drawdown(bot._portfolio.total_usd),
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
            "portfolio_usd": bot._portfolio.total_usd,
            "balances": bot._portfolio.balances,
            "drawdown": bot._risk.get_drawdown(bot._portfolio.total_usd),
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
