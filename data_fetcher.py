import yfinance as yf
import pandas as pd
from datetime import datetime, timezone


# ─── Real-time Quote ─────────────────────────────────────────────────────────

def get_realtime_quote(ticker: str) -> dict:
    """
    Fetch the most current available price via yfinance fast_info.
    Yahoo Finance provides data with a ~15-min delay for free users;
    this is the freshest data available without a paid API.
    Returns a dict with price, change, volume, market state, etc.
    """
    t = yf.Ticker(ticker)
    fi = t.fast_info
    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    return {
        "ticker":          ticker.upper(),
        "last_price":      _safe(fi, "last_price"),
        "previous_close":  _safe(fi, "previous_close"),
        "open":            _safe(fi, "open"),
        "day_high":        _safe(fi, "day_high"),
        "day_low":         _safe(fi, "day_low"),
        "last_volume":     _safe(fi, "last_volume"),
        "market_cap":      _safe(fi, "market_cap"),
        "fifty_day_avg":   _safe(fi, "fifty_day_average"),
        "two_hundred_avg": _safe(fi, "two_hundred_day_average"),
        "52w_high":        _safe(fi, "year_high"),
        "52w_low":         _safe(fi, "year_low"),
        "currency":        getattr(fi, "currency", "USD"),
        "exchange":        getattr(fi, "exchange", "—"),
        "timezone":        getattr(fi, "timezone", "—"),
        # Derived
        "change":          (_safe(fi, "last_price") or 0) - (_safe(fi, "previous_close") or 0),
        "pct_change":      (
            ((_safe(fi, "last_price") or 0) - (_safe(fi, "previous_close") or 0))
            / (_safe(fi, "previous_close") or 1)
        ) * 100,
        "fetched_at":      fetched_at,
        # From .info (slower but has market state)
        "market_state":    info.get("marketState", "UNKNOWN"),
        "pre_market_price":     info.get("preMarketPrice"),
        "post_market_price":    info.get("postMarketPrice"),
        "pre_market_change":    info.get("preMarketChangePercent"),
        "post_market_change":   info.get("postMarketChangePercent"),
        "regular_market_price": info.get("regularMarketPrice"),
        "short_name":           info.get("shortName", ticker),
    }


def _safe(obj, attr):
    try:
        v = getattr(obj, attr)
        return None if (v is None or (isinstance(v, float) and v != v)) else v
    except Exception:
        return None


# ─── Intraday Data ────────────────────────────────────────────────────────────

_INTRADAY_INTERVALS = {
    "1 min":  "1m",
    "5 min":  "5m",
    "15 min": "15m",
    "30 min": "30m",
    "1 hour": "60m",
}

def get_intraday_data(ticker: str, interval_label: str = "5 min") -> pd.DataFrame:
    """
    Fetch intraday OHLCV data for today (or last trading day).
    interval_label: one of '1 min', '5 min', '15 min', '30 min', '1 hour'
    Note: Yahoo Finance provides intraday data with ~15-min delay.
    """
    interval = _INTRADAY_INTERVALS.get(interval_label, "5m")
    df = yf.download(
        ticker,
        period="1d",
        interval=interval,
        progress=False,
        auto_adjust=True,
    )
    if df.empty:
        # Market may be closed; get last 5 trading days
        df = yf.download(
            ticker,
            period="5d",
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
    # Flatten MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = df.index.tz_convert("America/New_York")
    return df


# ─── Historical Data with Indicators ─────────────────────────────────────────

def fetch_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download raw OHLCV data using yfinance."""
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add full suite of technical indicators."""
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df["Close"]

    # Moving Averages
    df["SMA20"]  = close.rolling(20).mean()
    df["SMA50"]  = close.rolling(50).mean()
    df["SMA200"] = close.rolling(200).mean()
    df["EMA12"]  = close.ewm(span=12, adjust=False).mean()
    df["EMA26"]  = close.ewm(span=26, adjust=False).mean()

    # MACD
    df["MACD"]        = df["EMA12"] - df["EMA26"]
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"]   = df["MACD"] - df["MACD_Signal"]

    # RSI (14)
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, float("nan"))
    df["RSI"] = 100 - (100 / (1 + rs))

    # Stochastic RSI
    rsi_min = df["RSI"].rolling(14).min()
    rsi_max = df["RSI"].rolling(14).max()
    df["Stoch_RSI"] = (df["RSI"] - rsi_min) / (rsi_max - rsi_min + 1e-9)

    # Bollinger Bands (20, ±2σ)
    bb_mid         = close.rolling(20).mean()
    bb_std         = close.rolling(20).std()
    df["BB_Upper"]  = bb_mid + 2 * bb_std
    df["BB_Middle"] = bb_mid
    df["BB_Lower"]  = bb_mid - 2 * bb_std
    df["BB_Width"]  = (df["BB_Upper"] - df["BB_Lower"]) / bb_mid

    # ATR (14)
    high, low = df["High"], df["Low"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()

    # Volume
    df["Volume_MA20"] = df["Volume"].rolling(20).mean()
    df["Daily_Return"] = close.pct_change() * 100
    df["Volatility_30"] = df["Daily_Return"].rolling(30).std() * (252 ** 0.5)

    # OBV (On-Balance Volume)
    obv = [0]
    for i in range(1, len(df)):
        if close.iloc[i] > close.iloc[i - 1]:
            obv.append(obv[-1] + df["Volume"].iloc[i])
        elif close.iloc[i] < close.iloc[i - 1]:
            obv.append(obv[-1] - df["Volume"].iloc[i])
        else:
            obv.append(obv[-1])
    df["OBV"] = obv

    return df


def get_latest_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch and enrich historical data."""
    raw = fetch_data(ticker, start, end)
    if raw.empty:
        raise ValueError(f"No data returned for '{ticker}'. Check the symbol and date range.")
    return add_indicators(raw)


# ─── Company & Fundamental Data ──────────────────────────────────────────────

def get_ticker_info(ticker: str) -> dict:
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


def get_financials(ticker: str):
    t = yf.Ticker(ticker)
    try:
        return t.financials, t.balance_sheet, t.cashflow
    except Exception:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


def get_news(ticker: str) -> list:
    try:
        return yf.Ticker(ticker).news or []
    except Exception:
        return []


def get_institutional_holders(ticker: str) -> pd.DataFrame:
    try:
        return yf.Ticker(ticker).institutional_holders
    except Exception:
        return pd.DataFrame()


def get_analyst_recommendations(ticker: str) -> pd.DataFrame:
    try:
        return yf.Ticker(ticker).recommendations
    except Exception:
        return pd.DataFrame()


def get_options_dates(ticker: str):
    t = yf.Ticker(ticker)
    try:
        dates = t.options
        if not dates:
            return [], pd.DataFrame(), pd.DataFrame()
        chain = t.option_chain(dates[0])
        return list(dates), chain.calls, chain.puts
    except Exception:
        return [], pd.DataFrame(), pd.DataFrame()


def get_earnings(ticker: str) -> pd.DataFrame:
    try:
        return yf.Ticker(ticker).earnings_dates
    except Exception:
        return pd.DataFrame()
