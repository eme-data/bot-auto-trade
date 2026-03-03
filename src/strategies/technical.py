import pandas as pd

from ..utils.config import TechnicalConfig
from .base import BaseStrategy, Signal, SignalAction


class TechnicalStrategy(BaseStrategy):
    MIN_CONFIDENCE = 0.6

    def evaluate(self, df: pd.DataFrame, pair: str, current_price: float) -> Signal:
        if len(df) < 2:
            return self._hold(pair, "Insufficient data")

        last = df.iloc[-1]
        prev = df.iloc[-2]
        cfg: TechnicalConfig = self.config

        votes_buy = 0
        votes_sell = 0
        total_votes = 0
        reasons: list[str] = []

        # --- RSI ---
        rsi_col = f"RSI_{cfg.rsi_period}"
        if rsi_col in df.columns and pd.notna(last[rsi_col]):
            total_votes += 1
            if last[rsi_col] < cfg.rsi_oversold:
                votes_buy += 1
                reasons.append(f"RSI={last[rsi_col]:.1f} oversold")
            elif last[rsi_col] > cfg.rsi_overbought:
                votes_sell += 1
                reasons.append(f"RSI={last[rsi_col]:.1f} overbought")

        # --- MACD histogram crossover ---
        macd_hist_col = f"MACDh_{cfg.macd_fast}_{cfg.macd_slow}_{cfg.macd_signal}"
        if macd_hist_col in df.columns and pd.notna(last.get(macd_hist_col)):
            total_votes += 1
            hist_now = last[macd_hist_col]
            hist_prev = prev[macd_hist_col]
            if pd.notna(hist_prev):
                if hist_prev < 0 < hist_now:
                    votes_buy += 1
                    reasons.append("MACD histogram bullish cross")
                elif hist_prev > 0 > hist_now:
                    votes_sell += 1
                    reasons.append("MACD histogram bearish cross")

        # --- Bollinger Bands ---
        bb_lower = f"BBL_{cfg.bb_period}_{float(cfg.bb_std)}"
        bb_upper = f"BBU_{cfg.bb_period}_{float(cfg.bb_std)}"
        if bb_lower in df.columns and bb_upper in df.columns:
            if pd.notna(last.get(bb_lower)) and pd.notna(last.get(bb_upper)):
                total_votes += 1
                if current_price <= last[bb_lower]:
                    votes_buy += 1
                    reasons.append("Price at lower Bollinger Band")
                elif current_price >= last[bb_upper]:
                    votes_sell += 1
                    reasons.append("Price at upper Bollinger Band")

        # --- MA Crossover ---
        sma_fast_col = f"SMA_{cfg.ma_fast}"
        sma_slow_col = f"SMA_{cfg.ma_slow}"
        if sma_fast_col in df.columns and sma_slow_col in df.columns:
            fast_now = last.get(sma_fast_col)
            fast_prev = prev.get(sma_fast_col)
            slow_now = last.get(sma_slow_col)
            slow_prev = prev.get(sma_slow_col)
            if all(pd.notna(v) for v in (fast_now, fast_prev, slow_now, slow_prev)):
                total_votes += 1
                if fast_prev < slow_prev and fast_now > slow_now:
                    votes_buy += 1
                    reasons.append(f"SMA{cfg.ma_fast} crossed above SMA{cfg.ma_slow}")
                elif fast_prev > slow_prev and fast_now < slow_now:
                    votes_sell += 1
                    reasons.append(f"SMA{cfg.ma_fast} crossed below SMA{cfg.ma_slow}")

        if total_votes == 0:
            return self._hold(pair, "No indicators computed")

        buy_conf = votes_buy / total_votes
        sell_conf = votes_sell / total_votes

        if buy_conf >= self.MIN_CONFIDENCE:
            return Signal(
                action=SignalAction.BUY,
                pair=pair,
                strategy="TechnicalStrategy",
                confidence=buy_conf,
                reason=", ".join(reasons),
            )
        elif sell_conf >= self.MIN_CONFIDENCE:
            return Signal(
                action=SignalAction.SELL,
                pair=pair,
                strategy="TechnicalStrategy",
                confidence=sell_conf,
                reason=", ".join(reasons),
            )

        return self._hold(
            pair,
            f"Low confidence (buy={buy_conf:.2f}, sell={sell_conf:.2f})",
        )
