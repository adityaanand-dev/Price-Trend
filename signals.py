"""
signals.py — Technical analysis signal engine.

Each signal function returns a dict:
    {
        "name":        str,       # Signal name
        "signal":      str,       # "BUY" | "SELL" | "HOLD" | "NEUTRAL"
        "score":       int,       # +1 = bullish, -1 = bearish, 0 = neutral
        "strength":    str,       # "Strong" | "Moderate" | "Weak"
        "reason":      str,       # Human-readable explanation
        "value":       float|str  # The raw indicator value
    }

composite_signal() aggregates all signals into a final verdict.
"""

import pandas as pd
import numpy as np


# ─── Individual Signal Functions ────────────────────────────────────────────

def rsi_signal(df: pd.DataFrame) -> dict:
    """RSI overbought / oversold signal."""
    col = "RSI"
    if col not in df.columns or df[col].dropna().empty:
        return _neutral("RSI", "RSI not available", "—")

    rsi = float(df[col].dropna().iloc[-1])

    if rsi < 25:
        return _sig("RSI", "BUY",  +1, "Strong", f"RSI={rsi:.1f} — deeply oversold (< 25)", rsi)
    elif rsi < 35:
        return _sig("RSI", "BUY",  +1, "Moderate", f"RSI={rsi:.1f} — oversold (< 35)", rsi)
    elif rsi < 45:
        return _sig("RSI", "BUY",  +1, "Weak", f"RSI={rsi:.1f} — mildly oversold", rsi)
    elif rsi > 75:
        return _sig("RSI", "SELL", -1, "Strong", f"RSI={rsi:.1f} — deeply overbought (> 75)", rsi)
    elif rsi > 65:
        return _sig("RSI", "SELL", -1, "Moderate", f"RSI={rsi:.1f} — overbought (> 65)", rsi)
    elif rsi > 55:
        return _sig("RSI", "SELL", -1, "Weak", f"RSI={rsi:.1f} — mildly overbought", rsi)
    else:
        return _sig("RSI", "HOLD",  0, "Neutral", f"RSI={rsi:.1f} — neutral zone (45–55)", rsi)


def macd_signal(df: pd.DataFrame) -> dict:
    """MACD line vs Signal line crossover."""
    if "MACD" not in df.columns or "MACD_Signal" not in df.columns:
        return _neutral("MACD", "MACD not available", "—")

    clean = df[["MACD", "MACD_Signal", "MACD_Hist"]].dropna()
    if len(clean) < 2:
        return _neutral("MACD", "Not enough data", "—")

    macd_now   = float(clean["MACD"].iloc[-1])
    sig_now    = float(clean["MACD_Signal"].iloc[-1])
    macd_prev  = float(clean["MACD"].iloc[-2])
    sig_prev   = float(clean["MACD_Signal"].iloc[-2])
    hist_now   = float(clean["MACD_Hist"].iloc[-1])

    crossed_above = macd_prev < sig_prev and macd_now >= sig_now
    crossed_below = macd_prev > sig_prev and macd_now <= sig_now

    if crossed_above:
        return _sig("MACD", "BUY",  +1, "Strong",
                    f"MACD crossed ABOVE signal ({macd_now:.2f} > {sig_now:.2f})", macd_now)
    elif crossed_below:
        return _sig("MACD", "SELL", -1, "Strong",
                    f"MACD crossed BELOW signal ({macd_now:.2f} < {sig_now:.2f})", macd_now)
    elif macd_now > sig_now:
        strength = "Moderate" if hist_now > 0.1 else "Weak"
        return _sig("MACD", "BUY",  +1, strength,
                    f"MACD above signal — bullish momentum (hist={hist_now:.2f})", macd_now)
    else:
        strength = "Moderate" if hist_now < -0.1 else "Weak"
        return _sig("MACD", "SELL", -1, strength,
                    f"MACD below signal — bearish momentum (hist={hist_now:.2f})", macd_now)


def sma_crossover_signal(df: pd.DataFrame) -> dict:
    """Golden Cross (SMA50 > SMA200) / Death Cross (SMA50 < SMA200)."""
    if "SMA50" not in df.columns or "SMA200" not in df.columns:
        return _neutral("SMA Cross", "SMA not available", "—")

    clean = df[["SMA50", "SMA200"]].dropna()
    if len(clean) < 2:
        return _neutral("SMA Cross", "Not enough data", "—")

    s50_now  = float(clean["SMA50"].iloc[-1])
    s200_now = float(clean["SMA200"].iloc[-1])
    s50_prev = float(clean["SMA50"].iloc[-2])
    s200_prev= float(clean["SMA200"].iloc[-2])

    if s50_prev <= s200_prev and s50_now > s200_now:
        return _sig("SMA Cross", "BUY",  +1, "Strong",
                    f"🌟 Golden Cross! SMA50 ({s50_now:.2f}) just crossed above SMA200 ({s200_now:.2f})", s50_now)
    elif s50_prev >= s200_prev and s50_now < s200_now:
        return _sig("SMA Cross", "SELL", -1, "Strong",
                    f"💀 Death Cross! SMA50 ({s50_now:.2f}) just crossed below SMA200 ({s200_now:.2f})", s50_now)
    elif s50_now > s200_now:
        gap = ((s50_now - s200_now) / s200_now) * 100
        return _sig("SMA Cross", "BUY",  +1, "Moderate",
                    f"SMA50 above SMA200 — uptrend ({gap:.1f}% gap)", s50_now)
    else:
        gap = ((s200_now - s50_now) / s200_now) * 100
        return _sig("SMA Cross", "SELL", -1, "Moderate",
                    f"SMA50 below SMA200 — downtrend ({gap:.1f}% gap)", s50_now)


def price_vs_sma_signal(df: pd.DataFrame) -> dict:
    """Price position relative to SMA20 and SMA50."""
    if "SMA20" not in df.columns or "SMA50" not in df.columns:
        return _neutral("Price/SMA", "SMA not available", "—")

    clean = df[["Close", "SMA20", "SMA50"]].dropna()
    if clean.empty:
        return _neutral("Price/SMA", "Not enough data", "—")

    price = float(clean["Close"].iloc[-1])
    s20   = float(clean["SMA20"].iloc[-1])
    s50   = float(clean["SMA50"].iloc[-1])

    if price > s20 > s50:
        return _sig("Price/SMA", "BUY",  +1, "Strong",
                    f"Price (${price:.2f}) > SMA20 (${s20:.2f}) > SMA50 (${s50:.2f})", price)
    elif price < s20 < s50:
        return _sig("Price/SMA", "SELL", -1, "Strong",
                    f"Price (${price:.2f}) < SMA20 (${s20:.2f}) < SMA50 (${s50:.2f})", price)
    elif price > s50:
        return _sig("Price/SMA", "BUY",  +1, "Weak",
                    f"Price above SMA50 — mild bullish bias", price)
    else:
        return _sig("Price/SMA", "SELL", -1, "Weak",
                    f"Price below SMA50 — mild bearish bias", price)


def bollinger_signal(df: pd.DataFrame) -> dict:
    """Bollinger Band mean-reversion signal."""
    cols = ["Close", "BB_Upper", "BB_Lower", "BB_Middle", "BB_Width"]
    if not all(c in df.columns for c in cols):
        return _neutral("Bollinger", "BB not available", "—")

    clean = df[cols].dropna()
    if clean.empty:
        return _neutral("Bollinger", "Not enough data", "—")

    price  = float(clean["Close"].iloc[-1])
    upper  = float(clean["BB_Upper"].iloc[-1])
    lower  = float(clean["BB_Lower"].iloc[-1])
    middle = float(clean["BB_Middle"].iloc[-1])
    width  = float(clean["BB_Width"].iloc[-1])

    pct_b  = (price - lower) / (upper - lower) if upper != lower else 0.5

    if price <= lower:
        return _sig("Bollinger", "BUY",  +1, "Strong",
                    f"Price at/below lower BB — oversold (%%B={pct_b:.2f})", pct_b)
    elif price >= upper:
        return _sig("Bollinger", "SELL", -1, "Strong",
                    f"Price at/above upper BB — overbought (%%B={pct_b:.2f})", pct_b)
    elif pct_b < 0.2:
        return _sig("Bollinger", "BUY",  +1, "Moderate",
                    f"Price near lower BB (%%B={pct_b:.2f})", pct_b)
    elif pct_b > 0.8:
        return _sig("Bollinger", "SELL", -1, "Moderate",
                    f"Price near upper BB (%%B={pct_b:.2f})", pct_b)
    else:
        return _sig("Bollinger", "HOLD",  0, "Neutral",
                    f"Price within bands (%%B={pct_b:.2f}, width={width:.3f})", pct_b)


def volume_signal(df: pd.DataFrame) -> dict:
    """Volume confirmation — high volume validates the trend."""
    if "Volume" not in df.columns or "Volume_MA20" not in df.columns:
        return _neutral("Volume", "Volume data not available", "—")

    clean = df[["Volume", "Volume_MA20", "Daily_Return"]].dropna()
    if len(clean) < 2:
        return _neutral("Volume", "Not enough data", "—")

    vol_now  = float(clean["Volume"].iloc[-1])
    vol_ma   = float(clean["Volume_MA20"].iloc[-1])
    ret_now  = float(clean["Daily_Return"].iloc[-1])
    ratio    = vol_now / vol_ma if vol_ma else 1.0

    if ratio > 1.5 and ret_now > 0:
        return _sig("Volume", "BUY",  +1, "Strong",
                    f"High volume ({ratio:.1f}x avg) on up day — strong buying", vol_now)
    elif ratio > 1.5 and ret_now < 0:
        return _sig("Volume", "SELL", -1, "Strong",
                    f"High volume ({ratio:.1f}x avg) on down day — strong selling", vol_now)
    elif ratio > 1.2 and ret_now > 0:
        return _sig("Volume", "BUY",  +1, "Moderate",
                    f"Above-average volume on up day ({ratio:.1f}x)", vol_now)
    elif ratio > 1.2 and ret_now < 0:
        return _sig("Volume", "SELL", -1, "Moderate",
                    f"Above-average volume on down day ({ratio:.1f}x)", vol_now)
    else:
        return _sig("Volume", "HOLD", 0, "Neutral",
                    f"Normal volume ({ratio:.1f}x avg)", vol_now)


def trend_signal(df: pd.DataFrame) -> dict:
    """Short-term trend: 5-day vs 20-day price momentum."""
    if "Close" not in df.columns or len(df) < 20:
        return _neutral("Trend", "Not enough data", "—")

    close = df["Close"].dropna()
    m5    = float(close.iloc[-5:].mean())
    m20   = float(close.iloc[-20:].mean())
    price = float(close.iloc[-1])
    pct   = ((m5 - m20) / m20) * 100 if m20 else 0

    if pct > 2:
        return _sig("Trend", "BUY",  +1, "Strong",
                    f"5-day avg ${m5:.2f} is {pct:.1f}% above 20-day avg — strong uptrend", pct)
    elif pct > 0.5:
        return _sig("Trend", "BUY",  +1, "Moderate",
                    f"Short-term uptrend (5d avg {pct:.1f}% above 20d avg)", pct)
    elif pct < -2:
        return _sig("Trend", "SELL", -1, "Strong",
                    f"5-day avg ${m5:.2f} is {abs(pct):.1f}% below 20-day avg — strong downtrend", pct)
    elif pct < -0.5:
        return _sig("Trend", "SELL", -1, "Moderate",
                    f"Short-term downtrend (5d avg {abs(pct):.1f}% below 20d avg)", pct)
    else:
        return _sig("Trend", "HOLD", 0, "Neutral",
                    f"No clear short-term trend ({pct:.2f}%)", pct)


# ─── Composite Signal ────────────────────────────────────────────────────────

def composite_signal(df: pd.DataFrame) -> dict:
    """
    Run all signals and compute a weighted composite verdict.

    Returns:
        {
            "verdict":    "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL",
            "score":      float,       # normalised -1.0 to +1.0
            "bull_count": int,
            "bear_count": int,
            "neutral_count": int,
            "signals":    list[dict],  # individual signal results
        }
    """
    weights = {
        "RSI":      1.5,
        "MACD":     2.0,
        "SMA Cross":2.0,
        "Price/SMA":1.0,
        "Bollinger":1.5,
        "Volume":   1.0,
        "Trend":    1.5,
    }

    runners = {
        "RSI":       rsi_signal,
        "MACD":      macd_signal,
        "SMA Cross": sma_crossover_signal,
        "Price/SMA": price_vs_sma_signal,
        "Bollinger": bollinger_signal,
        "Volume":    volume_signal,
        "Trend":     trend_signal,
    }

    results   = []
    total_w   = 0.0
    weighted_score = 0.0
    bull = bear = neutral = 0

    for name, fn in runners.items():
        sig = fn(df)
        results.append(sig)
        w = weights.get(name, 1.0)
        weighted_score += sig["score"] * w
        total_w += w
        if sig["score"] > 0:  bull    += 1
        elif sig["score"] < 0: bear   += 1
        else:                  neutral += 1

    norm = weighted_score / total_w if total_w else 0.0

    if norm >= 0.55:
        verdict = "STRONG BUY"
    elif norm >= 0.20:
        verdict = "BUY"
    elif norm <= -0.55:
        verdict = "STRONG SELL"
    elif norm <= -0.20:
        verdict = "SELL"
    else:
        verdict = "HOLD"

    return {
        "verdict":       verdict,
        "score":         norm,
        "bull_count":    bull,
        "bear_count":    bear,
        "neutral_count": neutral,
        "signals":       results,
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sig(name, signal, score, strength, reason, value):
    return {"name": name, "signal": signal, "score": score,
            "strength": strength, "reason": reason, "value": value}

def _neutral(name, reason, value):
    return {"name": name, "signal": "NEUTRAL", "score": 0,
            "strength": "—", "reason": reason, "value": value}
