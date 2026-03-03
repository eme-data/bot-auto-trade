import os
from dataclasses import dataclass
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class BotConfig:
    dry_run: bool
    trading_pairs: list[str]
    poll_interval_seconds: int


@dataclass
class RiskConfig:
    max_position_pct: float
    stop_loss_pct: float
    max_drawdown_pct: float
    max_open_positions: int


@dataclass
class TechnicalConfig:
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    macd_fast: int
    macd_slow: int
    macd_signal: int
    bb_period: int
    bb_std: float
    ma_fast: int
    ma_slow: int
    timeframe: int
    lookback_candles: int


@dataclass
class GridConfig:
    enabled_pairs: list[str]
    grid_levels: int
    grid_spacing_pct: float
    total_investment_usd: float


@dataclass
class StrategiesConfig:
    active: str
    technical: TechnicalConfig
    grid: GridConfig


@dataclass
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass
class AppConfig:
    api_key: str
    api_secret: str
    bot: BotConfig
    risk: RiskConfig
    strategies: StrategiesConfig
    dashboard: DashboardConfig


def load_config(
    env_path: str = ".env",
    settings_path: str = "config/settings.yaml",
) -> AppConfig:
    load_dotenv(env_path)
    api_key = os.environ["KRAKEN_API_KEY"]
    api_secret = os.environ["KRAKEN_API_SECRET"]

    with open(settings_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    dash_raw = raw.get("dashboard", {})

    return AppConfig(
        api_key=api_key,
        api_secret=api_secret,
        bot=BotConfig(**raw["bot"]),
        risk=RiskConfig(**raw["risk"]),
        strategies=StrategiesConfig(
            active=raw["strategies"]["active"],
            technical=TechnicalConfig(**raw["strategies"]["technical"]),
            grid=GridConfig(**raw["strategies"]["grid"]),
        ),
        dashboard=DashboardConfig(**dash_raw),
    )
