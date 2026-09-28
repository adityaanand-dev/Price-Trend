import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime, timezone
import time

from data_fetcher import (
    get_realtime_quote, get_intraday_data, get_latest_data,
    get_ticker_info, get_financials, get_news,
    get_institutional_holders, get_analyst_recommendations,
    get_options_dates,
)
from alert_utils import price_crosses_threshold
from signals import composite_signal

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Price Trend",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Dark Theme CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"]        { font-size: 1.15rem !important; }
[data-testid="stMetricDelta"]        { font-size: 0.85rem !important; }
.section-header {
    font-size: 1.2rem; font-weight: 700; color: #a8d8ea;
    border-bottom: 2px solid #a8d8ea44; padding-bottom: 4px;
    margin: 1.2rem 0 0.6rem 0;
}
.verdict-box {
    text-align: center; padding: 18px 12px; border-radius: 12px;
    font-size: 1.6rem; font-weight: 800; letter-spacing: 2px;
}
.sig-row { padding: 6px 0; border-bottom: 1px solid #ffffff11; }
.news-card {
    background: #1e1e2e; border-left: 4px solid #a8d8ea;
    padding: 10px 14px; border-radius: 6px; margin-bottom: 8px;
}
.data-badge {
    display:inline-block; padding:3px 10px; border-radius:20px;
    font-size:0.75rem; font-weight:600; margin-left:8px;
}
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Configuration")
ticker      = st.sidebar.text_input("Stock Ticker", "AAPL").upper().strip()
start_date  = st.sidebar.date_input("Start Date", datetime(2022, 1, 1))
end_date    = st.sidebar.date_input("End Date", datetime.today())
intraday_iv = st.sidebar.selectbox("Intraday Interval", ["1 min","5 min","15 min","30 min","1 hour"])
refresh_opt = st.sidebar.selectbox("Auto Refresh", ["None","1 min","5 min","15 min"])

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Chart Overlays")
show_sma    = st.sidebar.checkbox("SMA 20 / 50 / 200",   value=True)
show_bb     = st.sidebar.checkbox("Bollinger Bands",       value=False)
show_volume = st.sidebar.checkbox("Volume Panel",          value=True)
show_macd   = st.sidebar.checkbox("MACD Panel",            value=True)
show_rsi    = st.sidebar.checkbox("RSI Panel",             value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("🔔 Price Alert")
alert_price     = st.sidebar.number_input("Alert Price ($)", min_value=0.0, value=0.0, step=1.0)
alert_direction = st.sidebar.selectbox("Direction", ["Above", "Below"])

start_str = start_date.strftime("%Y-%m-%d")
end_str   = end_date.strftime("%Y-%m-%d")
refresh_map = {"None": 0, "1 min": 60, "5 min": 300, "15 min": 900}
interval_sec = refresh_map[refresh_opt]

DARK_BG = "#0e1117"
plt.rcParams.update({"text.color": "white", "axes.labelcolor": "white",
                     "xtick.color": "white", "ytick.color": "white"})

# ─── Header ───────────────────────────────────────────────────────────────────
st.title(f"📈 Price Trend")

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK A — REAL-TIME QUOTE
# ══════════════════════════════════

with st.spinner("Fetching live quote…"):
    q = get_realtime_quote(ticker)

market_state = q.get("market_state", "UNKNOWN")
state_color  = {"REGULAR": "🟢", "PRE": "🟡", "POST": "🟠", "CLOSED": "🔴"}.get(market_state, "⚪")
st.caption(
    f"**{q.get('short_name', ticker)}** &nbsp;|&nbsp; "
    f"{state_color} Market: **{market_state}** &nbsp;|&nbsp; "
    f"Exchange: {q.get('exchange','—')} &nbsp;|&nbsp; "
    f"Last fetched: {q.get('fetched_at','—')} "
    f"*(Yahoo Finance ~15 min delayed during market hours)*"
)

lp  = q.get("last_price")
chg = q.get("change", 0) or 0
pct = q.get("pct_change", 0) or 0
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("Last Price",     f"${lp:.2f}"       if lp  else "—", f"{chg:+.2f} ({pct:+.2f}%)" if lp else None)
c2.metric("Open",           f"${q['open']:.2f}"         if q.get("open")        else "—")
c3.metric("Day High",       f"${q['day_high']:.2f}"     if q.get("day_high")    else "—")
c4.metric("Day Low",        f"${q['day_low']:.2f}"      if q.get("day_low")     else "—")
c5.metric("Prev Close",     f"${q['previous_close']:.2f}"if q.get("previous_close") else "—")
c6.metric("Volume",         f"{int(q['last_volume']):,}" if q.get("last_volume") else "—")
c7.metric("52W High/Low",
          f"${q['52w_high']:.2f}" if q.get("52w_high") else "—",
          f"/ ${q['52w_low']:.2f}" if q.get("52w_low") else None)

# Pre/Post market
pre  = q.get("pre_market_price")
post = q.get("post_market_price")
if pre or post:
    pm1, pm2 = st.columns(2)
    if pre:
        pre_chg = (q.get("pre_market_change") or 0) * 100
        pm1.metric("🌅 Pre-Market Price", f"${pre:.2f}", f"{pre_chg:+.2f}%")
    if post:
        post_chg = (q.get("post_market_change") or 0) * 100
        pm2.metric("🌆 After-Hours Price", f"${post:.2f}", f"{post_chg:+.2f}%")

# Alert
if alert_price > 0 and lp:
    if (alert_direction == "Above" and lp > alert_price) or \
       (alert_direction == "Below" and lp < alert_price):
        st.warning(f"🔔 **Alert triggered!** {ticker} is {'above' if alert_direction=='Above' else 'below'} "
                   f"${alert_price:.2f} — Current: ${lp:.2f}")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK B — INTRADAY CHART
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-header">🕐 Intraday Chart</div>', unsafe_allow_html=True)

with st.spinner("Fetching intraday data…"):
    idf = get_intraday_data(ticker, intraday_iv)

if idf is not None and not idf.empty:
    fig_i, (ax_i1, ax_i2) = plt.subplots(2, 1, figsize=(14, 6), sharex=True,
                                           gridspec_kw={"height_ratios": [3, 1]})
    fig_i.patch.set_facecolor(DARK_BG)
    for ax in (ax_i1, ax_i2):
        ax.set_facecolor(DARK_BG); ax.grid(alpha=0.1)

    close_i = idf["Close"].squeeze() if hasattr(idf["Close"], "squeeze") else idf["Close"]
    vol_i   = idf["Volume"].squeeze() if hasattr(idf["Volume"], "squeeze") else idf["Volume"]

    ax_i1.plot(idf.index, close_i, color="#00d4ff", linewidth=1.5, label=f"{intraday_iv} Close")
    ax_i1.fill_between(idf.index, close_i, close_i.min(), alpha=0.08, color="#00d4ff")
    ax_i1.set_ylabel("Price (USD)", fontsize=9)
    ax_i1.legend(fontsize=8, framealpha=0.3)
    title_date = idf.index[-1].strftime("%A, %d %b %Y") if len(idf) else "Recent"
    ax_i1.set_title(f"{ticker} — Intraday ({title_date})", fontsize=12)

    vol_colors = []
    for i in range(len(idf)):
        if i == 0:
            vol_colors.append("#00d4ff")
        else:
            vol_colors.append("#00d4ff" if close_i.iloc[i] >= close_i.iloc[i-1] else "#ff6b6b")
    ax_i2.bar(idf.index, vol_i, color=vol_colors, alpha=0.8, width=0.0005)
    ax_i2.set_ylabel("Volume", fontsize=9)
    ax_i2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.tight_layout()
    st.pyplot(fig_i)
    plt.close(fig_i)

    last_intraday = idf.index[-1].strftime("%Y-%m-%d %H:%M %Z") if len(idf) else "—"
    st.caption(f"⏱️ Most recent intraday bar: **{last_intraday}** (Yahoo Finance ~15 min delay during market hours)")
else:
    st.info("Intraday data not available — market may be closed.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK C — HISTORICAL DATA + INDICATORS
# ══════════════════════════════════════════════════════════════════════════════
try:
    with st.spinner("Fetching historical data…"):
        df = get_latest_data(ticker, start_str, end_str)

    # ── Company Overview ──────────────────────────────────────────────────────
    with st.spinner("Fetching company info…"):
        info = get_ticker_info(ticker)

    if info:
        st.markdown('<div class="section-header">🏢 Company Overview</div>', unsafe_allow_html=True)
        ca, cb, cc, cd = st.columns(4)
        ca.metric("Company",  info.get("longName", ticker))
        cb.metric("Sector",   info.get("sector",   "—"))
        cc.metric("Industry", info.get("industry", "—"))
        cd.metric("Country",  info.get("country",  "—"))

        ca, cb, cc, cd, ce = st.columns(5)
        mc = info.get("marketCap", 0) or 0
        ca.metric("Market Cap",     f"${mc/1e9:.2f}B")
        cb.metric("P/E Ratio",      f"{info.get('trailingPE', '—')}")
        cc.metric("EPS (TTM)",      f"${info.get('trailingEps', '—')}")
        div = info.get("dividendYield")
        cd.metric("Dividend Yield", f"{div*100:.2f}%" if div else "—")
        ce.metric("Beta",           f"{info.get('beta', '—')}")

        with st.expander("📝 Business Summary"):
            st.write(info.get("longBusinessSummary", "No description available."))

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCK D — BUY / SELL SIGNALS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">🎯 Buy / Sell Signal Analysis</div>', unsafe_allow_html=True)

    comp = composite_signal(df)
    verdict = comp["verdict"]

    verdict_styles = {
        "STRONG BUY":  ("background:#0d6e2e; color:#00ff88;", "🟢"),
        "BUY":         ("background:#145a32; color:#7dff7d;", "🟢"),
        "HOLD":        ("background:#444;     color:#ffdd57;", "🟡"),
        "SELL":        ("background:#6e1a0d; color:#ff8080;", "🔴"),
        "STRONG SELL": ("background:#4a0a0a; color:#ff4444;", "🔴"),
    }
    vstyle, vicon = verdict_styles.get(verdict, ("background:#333; color:white;", "⚪"))

    col_v, col_gauge = st.columns([1, 2])

    with col_v:
        st.markdown(
            f'<div class="verdict-box" style="{vstyle}">'
            f'{vicon} {verdict}</div>',
            unsafe_allow_html=True
        )
        score_pct = (comp["score"] + 1) / 2 * 100  # map -1..+1 → 0..100
        st.progress(int(score_pct), text=f"Signal Strength: {comp['score']:+.2f}")
        st.caption(
            f"🟢 Bullish: **{comp['bull_count']}**  &nbsp; "
            f"🔴 Bearish: **{comp['bear_count']}**  &nbsp; "
            f"🟡 Neutral: **{comp['neutral_count']}**"
        )

    with col_gauge:
        # Horizontal bar chart of individual signals
        sig_names   = [s["name"]   for s in comp["signals"]]
        sig_scores  = [s["score"]  for s in comp["signals"]]
        sig_colors  = ["#00d4ff" if s > 0 else "#ff6b6b" if s < 0 else "#888" for s in sig_scores]

        fig_s, ax_s = plt.subplots(figsize=(7, 3.2))
        fig_s.patch.set_facecolor(DARK_BG)
        ax_s.set_facecolor(DARK_BG)
        bars = ax_s.barh(sig_names, sig_scores, color=sig_colors, height=0.5)
        ax_s.axvline(0, color="white", linewidth=0.8, alpha=0.5)
        ax_s.set_xlim(-1.2, 1.2)
        ax_s.set_xlabel("Signal Score (−1 = Sell, +1 = Buy)", fontsize=8)
        ax_s.tick_params(labelsize=9)
        ax_s.grid(axis="x", alpha=0.1)
        ax_s.set_title("Individual Signal Scores", fontsize=10)
        plt.tight_layout()
        st.pyplot(fig_s)
        plt.close(fig_s)

    # Signal detail table
    st.markdown("**Signal Breakdown:**")
    rows = []
    for s in comp["signals"]:
        sig = s["signal"]
        icon = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "HOLD": "🟡 HOLD", "NEUTRAL": "⚪ —"}.get(sig, sig)
        rows.append({
            "Indicator": s["name"],
            "Signal":    icon,
            "Strength":  s["strength"],
            "Reason":    s["reason"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCK E — PRICE CHART WITH SIGNAL MARKERS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">📊 Price Chart</div>', unsafe_allow_html=True)

    n_sub = 1 + show_volume + show_macd + show_rsi
    h_rat = [4] + [1.2] * (n_sub - 1)
    fig, axes = plt.subplots(n_sub, 1, figsize=(14, 4 + 2.5 * n_sub),
                              sharex=True, gridspec_kw={"height_ratios": h_rat})
    if n_sub == 1:
        axes = [axes]
    fig.patch.set_facecolor(DARK_BG)
    for ax in axes:
        ax.set_facecolor(DARK_BG); ax.grid(alpha=0.08)

    ax0 = axes[0]
    close_s = df["Close"].squeeze() if hasattr(df["Close"],"squeeze") else df["Close"]
    ax0.plot(df.index, close_s, color="#00d4ff", linewidth=1.4, label="Close", zorder=3)

    if show_sma:
        for col, color, lbl in [("SMA20","#f5a623","SMA20"),
                                 ("SMA50","#7ed321","SMA50"),
                                 ("SMA200","#ff6b6b","SMA200")]:
            if col in df.columns:
                ax0.plot(df.index, df[col].squeeze(), color=color, linewidth=1,
                         linestyle="--", label=lbl, alpha=0.85)

    if show_bb and all(c in df.columns for c in ["BB_Upper","BB_Lower","BB_Middle"]):
        ax0.fill_between(df.index, df["BB_Lower"].squeeze(), df["BB_Upper"].squeeze(),
                         alpha=0.08, color="#a8d8ea")
        for col, lw in [("BB_Upper",0.8),("BB_Lower",0.8),("BB_Middle",0.7)]:
            ax0.plot(df.index, df[col].squeeze(), color="#a8d8ea", linewidth=lw, linestyle=":")

    # Mark Buy/Sell on chart using MACD crossovers
    if "MACD" in df.columns and "MACD_Signal" in df.columns:
        macd  = df["MACD"].squeeze()
        msig  = df["MACD_Signal"].squeeze()
        buy_x  = df.index[(macd > msig) & (macd.shift() <= msig.shift())]
        sell_x = df.index[(macd < msig) & (macd.shift() >= msig.shift())]
        buy_y  = close_s.reindex(buy_x)
        sell_y = close_s.reindex(sell_x)
        ax0.scatter(buy_x,  buy_y,  marker="^", color="#00ff88", s=60, zorder=5, label="MACD Buy ▲")
        ax0.scatter(sell_x, sell_y, marker="v", color="#ff4444", s=60, zorder=5, label="MACD Sell ▼")

    ax0.set_ylabel("Price (USD)", fontsize=9)
    ax0.legend(loc="upper left", fontsize=7.5, framealpha=0.25)
    ax0.set_title(f"{ticker}  |  {start_str} → {end_str}", fontsize=12)

    sub = 1
    if show_volume:
        axv = axes[sub]; sub += 1
        ret  = df["Daily_Return"].squeeze() if "Daily_Return" in df.columns else pd.Series(0, index=df.index)
        vcol = ["#00d4ff" if r >= 0 else "#ff6b6b" for r in ret.fillna(0)]
        axv.bar(df.index, df["Volume"].squeeze(), color=vcol, alpha=0.7, width=1)
        if "Volume_MA20" in df.columns:
            axv.plot(df.index, df["Volume_MA20"].squeeze(), color="#f5a623", linewidth=0.9, label="Vol MA20")
        axv.set_ylabel("Volume", fontsize=8); axv.legend(fontsize=7, framealpha=0.2)

    if show_macd and "MACD" in df.columns:
        axm = axes[sub]; sub += 1
        axm.plot(df.index, df["MACD"].squeeze(),        color="#00d4ff", linewidth=1,   label="MACD")
        axm.plot(df.index, df["MACD_Signal"].squeeze(), color="#f5a623", linewidth=1,   label="Signal")
        hcol = ["#00d4ff" if v >= 0 else "#ff6b6b" for v in df["MACD_Hist"].fillna(0).squeeze()]
        axm.bar(df.index, df["MACD_Hist"].squeeze(), color=hcol, alpha=0.45, width=1)
        axm.axhline(0, color="white", linewidth=0.5, alpha=0.4)
        axm.set_ylabel("MACD", fontsize=8); axm.legend(fontsize=7, framealpha=0.2)

    if show_rsi and "RSI" in df.columns:
        axr = axes[sub]; sub += 1
        axr.plot(df.index, df["RSI"].squeeze(), color="#a8d8ea", linewidth=1, label="RSI 14")
        axr.axhline(70, color="#ff6b6b", linewidth=0.8, linestyle="--", alpha=0.7, label="OB 70")
        axr.axhline(30, color="#7ed321", linewidth=0.8, linestyle="--", alpha=0.7, label="OS 30")
        axr.fill_between(df.index, df["RSI"].squeeze(), 70, where=(df["RSI"].squeeze() >= 70), alpha=0.15, color="#ff6b6b")
        axr.fill_between(df.index, df["RSI"].squeeze(), 30, where=(df["RSI"].squeeze() <= 30), alpha=0.15, color="#7ed321")
        axr.set_ylim(0, 100)
        axr.set_ylabel("RSI", fontsize=8); axr.legend(fontsize=7, framealpha=0.2)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCK F — KEY METRICS SNAPSHOT
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">📉 Performance & Volatility</div>', unsafe_allow_html=True)

    latest_close = float(df["Close"].iloc[-1].squeeze() if hasattr(df["Close"].iloc[-1], "squeeze") else df["Close"].iloc[-1])

    def pret(n):
        if len(df) > n:
            base = float(df["Close"].iloc[-n].squeeze() if hasattr(df["Close"].iloc[-n],"squeeze") else df["Close"].iloc[-n])
            return ((latest_close - base) / base) * 100 if base else None
        return None

    r1m, r3m, r6m, r1y = pret(22), pret(66), pret(132), pret(252)
    atr_v   = float(df["ATR"].dropna().iloc[-1])  if "ATR"          in df.columns else None
    vol30   = float(df["Volatility_30"].dropna().iloc[-1]) if "Volatility_30" in df.columns else None
    stochrsi= float(df["Stoch_RSI"].dropna().iloc[-1])     if "Stoch_RSI"     in df.columns else None
    rsi_cur = float(df["RSI"].dropna().iloc[-1])            if "RSI"           in df.columns else None

    c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
    c1.metric("Return 1M",   f"{r1m:+.1f}%"   if r1m  is not None else "—")
    c2.metric("Return 3M",   f"{r3m:+.1f}%"   if r3m  is not None else "—")
    c3.metric("Return 6M",   f"{r6m:+.1f}%"   if r6m  is not None else "—")
    c4.metric("Return 1Y",   f"{r1y:+.1f}%"   if r1y  is not None else "—")
    c5.metric("ATR (14)",    f"${atr_v:.2f}"   if atr_v   is not None else "—")
    c6.metric("Volatility",  f"{vol30:.1f}%"   if vol30   is not None else "—")
    c7.metric("Stoch RSI",   f"{stochrsi:.2f}" if stochrsi is not None else "—",
              "Overbought" if stochrsi and stochrsi > 0.8 else "Oversold" if stochrsi and stochrsi < 0.2 else "Neutral")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Daily Return Distribution**")
        fig2, ax2 = plt.subplots(figsize=(6, 2.8))
        fig2.patch.set_facecolor(DARK_BG); ax2.set_facecolor(DARK_BG)
        ret_data = df["Daily_Return"].dropna().squeeze()
        ax2.hist(ret_data, bins=60, color="#00d4ff", alpha=0.75, edgecolor="none")
        ax2.axvline(0, color="white", linewidth=0.8, linestyle="--")
        ax2.set_xlabel("Daily Return (%)", fontsize=8); ax2.set_ylabel("Frequency", fontsize=8)
        ax2.grid(alpha=0.08); plt.tight_layout(); st.pyplot(fig2); plt.close(fig2)

    with col2:
        st.markdown("**30-Day Rolling Annualised Volatility**")
        fig3, ax3 = plt.subplots(figsize=(6, 2.8))
        fig3.patch.set_facecolor(DARK_BG); ax3.set_facecolor(DARK_BG)
        vol_data = df["Volatility_30"].dropna().squeeze()
        ax3.plot(df.index[len(df)-len(vol_data):], vol_data, color="#f5a623", linewidth=1.2)
        ax3.fill_between(df.index[len(df)-len(vol_data):], vol_data, alpha=0.15, color="#f5a623")
        ax3.set_ylabel("Volatility (%)", fontsize=8)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax3.grid(alpha=0.08); plt.tight_layout(); st.pyplot(fig3); plt.close(fig3)

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCK G — DATA TABLE
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">📋 Historical Data & Indicators</div>', unsafe_allow_html=True)
    disp_cols = [c for c in ["Open","High","Low","Close","Volume","SMA20","SMA50","SMA200",
                              "RSI","MACD","BB_Upper","BB_Lower","ATR","OBV","Daily_Return"]
                 if c in df.columns]
    st.dataframe(
        df[disp_cols].tail(120).sort_index(ascending=False).style.format("{:.2f}"),
        use_container_width=True, height=300
    )
    with st.expander("📊 Statistical Summary"):
        st.dataframe(df[disp_cols].describe().style.format("{:.2f}"), use_container_width=True)

    st.divider()

except Exception as e:
    st.error(f"❌ Error loading historical data: {e}")
    st.exception(e)

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK H — FINANCIALS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-header">💰 Financial Statements</div>', unsafe_allow_html=True)
with st.spinner("Loading financials…"):
    income, balance, cashflow = get_financials(ticker)

tab1, tab2, tab3 = st.tabs(["Income Statement", "Balance Sheet", "Cash Flow"])
for tab, frame in [(tab1, income), (tab2, balance), (tab3, cashflow)]:
    with tab:
        if frame is not None and not frame.empty:
            st.dataframe(frame.style.format("{:,.0f}"), use_container_width=True)
        else:
            st.info("No data available.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK I — ANALYST + HOLDERS + OPTIONS
# ══════════════════════════════════════════════════════════════════════════════
col_a, col_b = st.columns(2)

with col_a:
    st.markdown('<div class="section-header">🧑‍💼 Analyst Recommendations</div>', unsafe_allow_html=True)
    with st.spinner("Loading…"):
        recs = get_analyst_recommendations(ticker)
    if recs is not None and not recs.empty:
        st.dataframe(recs.tail(20), use_container_width=True)
    else:
        st.info("No data available.")

with col_b:
    st.markdown('<div class="section-header">🏦 Institutional Holders</div>', unsafe_allow_html=True)
    with st.spinner("Loading…"):
        holders = get_institutional_holders(ticker)
    if holders is not None and not holders.empty:
        st.dataframe(holders, use_container_width=True)
    else:
        st.info("No data available.")

st.divider()

st.markdown('<div class="section-header">🎯 Options Chain</div>', unsafe_allow_html=True)
with st.spinner("Loading options…"):
    opt_dates, calls, puts = get_options_dates(ticker)
if opt_dates:
    sel_exp = st.selectbox("Expiry Date", opt_dates)
    ot1, ot2 = st.tabs(["📗 Calls", "📕 Puts"])
    for otab, odf in [(ot1, calls), (ot2, puts)]:
        with otab:
            cols_o = [c for c in ["strike","lastPrice","bid","ask","volume","openInterest","impliedVolatility"] if c in odf.columns]
            if not odf.empty:
                st.dataframe(odf[cols_o].style.format("{:.2f}"), use_container_width=True)
else:
    st.info("No options data available.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK J — NEWS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-header">📰 Latest News</div>', unsafe_allow_html=True)
with st.spinner("Loading news…"):
    news_items = get_news(ticker)

if news_items:
    for item in news_items[:12]:
        content   = item.get("content", {})
        title     = content.get("title", item.get("title", "No title"))
        url       = content.get("canonicalUrl", {}).get("url", "") or item.get("link", "#")
        pub       = content.get("pubDate", item.get("providerPublishTime", ""))
        publisher = content.get("provider", {}).get("displayName", item.get("publisher", ""))
        if pub and not isinstance(pub, str):
            try:    pub = datetime.fromtimestamp(int(pub)).strftime("%d %b %Y %H:%M")
            except: pub = str(pub)
        st.markdown(
            f'<div class="news-card">'
            f'<a href="{url}" target="_blank" style="color:#a8d8ea;font-weight:600;text-decoration:none;">{title}</a>'
            f'<br><small style="color:#888;">{publisher} &nbsp;·&nbsp; {pub}</small>'
            f'</div>',
            unsafe_allow_html=True
        )
else:
    st.info("No news available.")

# ─── Auto Refresh ─────────────────────────────────────────────────────────────
if interval_sec > 0:
    st.info(f"🔄 Auto-refreshing every {refresh_opt}…")
    time.sleep(interval_sec)
    st.rerun()