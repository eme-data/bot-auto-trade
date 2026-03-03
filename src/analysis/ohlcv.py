import pandas as pd

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "vwap", "volume", "count"]


def kraken_ohlcv_to_dataframe(raw: list[list]) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=OHLCV_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    for col in ("open", "high", "low", "close", "vwap", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["count"] = df["count"].astype(int)
    df = df.set_index("timestamp").sort_index()
    return df
