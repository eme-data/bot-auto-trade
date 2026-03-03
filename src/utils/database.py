import json
from pathlib import Path

import aiosqlite

DB_PATH = "data/trade_history.db"

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    txid        TEXT UNIQUE,
    pair        TEXT NOT NULL,
    side        TEXT NOT NULL,
    order_type  TEXT NOT NULL,
    price       REAL,
    volume      REAL NOT NULL,
    fee         REAL,
    strategy    TEXT,
    dry_run     INTEGER NOT NULL DEFAULT 1,
    timestamp   TEXT NOT NULL,
    raw_response TEXT
);

CREATE TABLE IF NOT EXISTS open_orders (
    txid        TEXT PRIMARY KEY,
    pair        TEXT NOT NULL,
    side        TEXT NOT NULL,
    order_type  TEXT NOT NULL,
    price       REAL,
    volume      REAL NOT NULL,
    strategy    TEXT,
    placed_at   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    balances    TEXT NOT NULL,
    total_usd   REAL,
    drawdown    REAL
);

CREATE TABLE IF NOT EXISTS ohlcv_cache (
    pair        TEXT NOT NULL,
    timeframe   INTEGER NOT NULL,
    timestamp   TEXT NOT NULL,
    open        REAL NOT NULL,
    high        REAL NOT NULL,
    low         REAL NOT NULL,
    close       REAL NOT NULL,
    volume      REAL NOT NULL,
    PRIMARY KEY (pair, timeframe, timestamp)
);
"""


async def init_db(db_path: str = DB_PATH) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()


async def insert_trade(trade: dict, db_path: str = DB_PATH) -> None:
    sql = """
        INSERT OR IGNORE INTO trades
        (txid, pair, side, order_type, price, volume, fee, strategy, dry_run, timestamp, raw_response)
        VALUES (:txid, :pair, :side, :order_type, :price, :volume, :fee, :strategy, :dry_run, :timestamp, :raw_response)
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, trade)
        await db.commit()


async def insert_ohlcv_batch(rows: list[dict], db_path: str = DB_PATH) -> None:
    sql = """
        INSERT OR REPLACE INTO ohlcv_cache
        (pair, timeframe, timestamp, open, high, low, close, volume)
        VALUES (:pair, :timeframe, :timestamp, :open, :high, :low, :close, :volume)
    """
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(sql, rows)
        await db.commit()


async def save_portfolio_snapshot(snapshot: dict, db_path: str = DB_PATH) -> None:
    sql = """
        INSERT INTO portfolio_snapshots (timestamp, balances, total_usd, drawdown)
        VALUES (:timestamp, :balances, :total_usd, :drawdown)
    """
    snapshot["balances"] = json.dumps(snapshot["balances"])
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, snapshot)
        await db.commit()
