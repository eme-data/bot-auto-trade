import pandas as pd
import pandas_ta_classic as ta  # noqa: F401 — registers .ta accessor on DataFrame


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df[f"RSI_{period}"] = df.ta.rsi(close="close", length=period)
    return df


def add_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    macd = df.ta.macd(close="close", fast=fast, slow=slow, signal=signal)
    df = pd.concat([df, macd], axis=1)
    return df


def add_bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std: float = 2.0,
) -> pd.DataFrame:
    bb = df.ta.bbands(close="close", length=period, std=std)
    df = pd.concat([df, bb], axis=1)
    return df


def add_moving_averages(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
) -> pd.DataFrame:
    df[f"SMA_{fast}"] = df.ta.sma(close="close", length=fast)
    df[f"SMA_{slow}"] = df.ta.sma(close="close", length=slow)
    return df


def compute_all_indicators(
    df: pd.DataFrame,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_period: int = 20,
    bb_std: float = 2.0,
    ma_fast: int = 20,
    ma_slow: int = 50,
) -> pd.DataFrame:
    df = add_rsi(df, rsi_period)
    df = add_macd(df, macd_fast, macd_slow, macd_signal)
    df = add_bollinger_bands(df, bb_period, bb_std)
    df = add_moving_averages(df, ma_fast, ma_slow)
    return df.dropna()
