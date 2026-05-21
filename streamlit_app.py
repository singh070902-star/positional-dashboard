"""
streamlit_app.py
----------------
Positional Portfolio Dashboard — reads from Google Sheets, displays live M2M.

Deploy on Streamlit Cloud:
  1. Push this file + requirements.txt to a GitHub repo
  2. Connect repo to Streamlit Cloud (share.streamlit.io)
  3. Add secrets in Streamlit Cloud dashboard:
       [gsheet]
       spreadsheet_id  = "YOUR_ID"
       credentials_json = '''{ ...service account JSON... }'''

Run locally:
  streamlit run streamlit_app.py
"""

import json
import time
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title = "Portfolio Dashboard",
    page_icon  = "📊",
    layout     = "wide",
    initial_sidebar_state = "collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  /* Dark trading terminal feel */
  .stApp { background-color: #0e1117; }
  .metric-card {
    background: #1c1f26;
    border-radius: 12px;
    padding: 18px 24px;
    border-left: 4px solid #00d4aa;
    margin-bottom: 8px;
  }
  .metric-label { color: #8b8fa8; font-size: 13px; font-weight: 500; }
  .metric-value { font-size: 28px; font-weight: 700; margin-top: 4px; }
  .positive { color: #00d4aa; }
  .negative { color: #ff4b6e; }
  .neutral  { color: #c9d1d9; }
  .section-header {
    color: #8b8fa8;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin: 24px 0 8px;
    border-bottom: 1px solid #21262d;
    padding-bottom: 6px;
  }
  /* Make dataframe blend in */
  .stDataFrame { border-radius: 8px; overflow: hidden; }
  div[data-testid="stMetricValue"] { font-size: 2rem !important; }
</style>
""", unsafe_allow_html=True)


# ── Google Sheets connection ──────────────────────────────────────────────────

@st.cache_resource
def _gsheet_client():
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    # Streamlit Cloud: read from st.secrets
    # Local: read from local credentials file
    try:
        creds_dict = json.loads(st.secrets["gsheet"]["credentials_json"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        spreadsheet_id = st.secrets["gsheet"]["spreadsheet_id"]
    except (KeyError, FileNotFoundError):
        # Fallback for local testing — set these env vars or edit directly
        import os
        creds_file = os.environ.get(
            "GSHEET_CREDS",
            r"C:\Users\Administrator\Desktop\gsheet_credentials.json"
        )
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        spreadsheet_id = os.environ.get("SPREADSHEET_ID", "YOUR_SPREADSHEET_ID_HERE")

    gc    = gspread.authorize(creds)
    sheet = gc.open_by_key(spreadsheet_id)
    return sheet


def _read_tab(tab_name: str) -> pd.DataFrame:
    try:
        sheet = _gsheet_client()
        ws    = sheet.worksheet(tab_name)
        data  = ws.get_all_values()
        if not data or len(data) < 2:
            return pd.DataFrame()
        df = pd.DataFrame(data[1:], columns=data[0])
        return df
    except Exception as e:
        st.warning(f"Could not load {tab_name}: {e}")
        return pd.DataFrame()


# ── Data helpers ──────────────────────────────────────────────────────────────

def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.str.replace(",", ""), errors="coerce").fillna(0.0)


def load_positions() -> pd.DataFrame:
    df = _read_tab("Positions")
    if df.empty:
        return df
    # Drop summary/blank rows
    df = df[df["Symbol"].str.strip().ne("") & df["Symbol"].ne("TOTAL")]
    for col in ["Lots", "Net Qty", "Avg Price", "LTP", "Open M2M (₹)", "Realized P&L (₹)", "Total P&L (₹)"]:
        if col in df.columns:
            df[col] = _to_float(df[col])
    return df


def load_closed() -> pd.DataFrame:
    df = _read_tab("ClosedPnL")
    if df.empty:
        return df
    df = df[df["Symbol"].str.strip().ne("") & ~df["Symbol"].str.startswith("──") & df["Symbol"].ne("GRAND TOTAL")]
    if "Realized P&L (₹)" in df.columns:
        df["Realized P&L (₹)"] = _to_float(df["Realized P&L (₹)"])
    return df


def load_daily() -> pd.DataFrame:
    df = _read_tab("DailyPnL")
    if df.empty:
        return df
    for col in ["Open M2M (₹)", "Realized P&L (₹)", "Total P&L (₹)"]:
        if col in df.columns:
            df[col] = _to_float(df[col])
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).sort_values("Date")
    return df


# ── Cumulative P&L from DailyPnL tab ─────────────────────────────────────────

def cumulative_pnl(daily: pd.DataFrame) -> dict:
    if daily.empty or "Date" not in daily.columns:
        return {"today": 0, "week": 0, "month": 0, "quarter": 0, "year": 0}

    today   = date.today()
    col     = "Total P&L (₹)"

    def pnl_since(d: date) -> float:
        mask = daily["Date"].dt.date >= d
        return float(daily.loc[mask, col].sum())

    week_start    = today - timedelta(days=today.weekday())
    month_start   = today.replace(day=1)
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = today.replace(month=quarter_month, day=1)
    year_start    = today.replace(month=1, day=1)

    return {
        "today":   pnl_since(today),
        "week":    pnl_since(week_start),
        "month":   pnl_since(month_start),
        "quarter": pnl_since(quarter_start),
        "year":    pnl_since(year_start),
    }


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt_pnl(val: float) -> str:
    sign = "+" if val > 0 else ""
    return f"{sign}₹{val:,.0f}"


def colour(val: float) -> str:
    return "positive" if val >= 0 else "negative"


def metric_card(label: str, value: str, css_class: str = "neutral"):
    st.markdown(
        f"""<div class="metric-card">
              <div class="metric-label">{label}</div>
              <div class="metric-value {css_class}">{value}</div>
            </div>""",
        unsafe_allow_html=True,
    )


# ── Main dashboard ────────────────────────────────────────────────────────────

def main():
    # ── Header ──
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.markdown("## 📊 Positional Portfolio")
        st.caption(f"Last loaded: {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
    with col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── Load data ──
    with st.spinner("Loading …"):
        positions = load_positions()
        closed    = load_closed()
        daily     = load_daily()

    # ── Aggregate metrics ──
    open_m2m      = float(positions["Open M2M (₹)"].sum()) if not positions.empty else 0.0
    realized_open = float(positions["Realized P&L (₹)"].sum()) if not positions.empty else 0.0
    realized_cl   = float(closed["Realized P&L (₹)"].sum()) if not closed.empty else 0.0
    total_realized = realized_open + realized_cl
    total_pnl      = open_m2m + total_realized
    cum            = cumulative_pnl(daily)

    # ── Row 1: Portfolio summary metrics ──
    st.markdown('<div class="section-header">Portfolio Overview</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Open M2M", fmt_pnl(open_m2m), colour(open_m2m))
    with c2:
        metric_card("Realized P&L", fmt_pnl(total_realized), colour(total_realized))
    with c3:
        metric_card("Net Total P&L", fmt_pnl(total_pnl), colour(total_pnl))
    with c4:
        metric_card("Open Positions", str(len(positions)), "neutral")

    # ── Row 2: Cumulative P&L ──
    st.markdown('<div class="section-header">Cumulative P&L</div>', unsafe_allow_html=True)
    cc1, cc2, cc3, cc4, cc5 = st.columns(5)
    for col_widget, label, key in [
        (cc1, "Today",   "today"),
        (cc2, "Week",    "week"),
        (cc3, "Month",   "month"),
        (cc4, "Quarter", "quarter"),
        (cc5, "Year",    "year"),
    ]:
        with col_widget:
            val = cum[key]
            metric_card(label, fmt_pnl(val), colour(val))

    # ── Tabs ──
    tab1, tab2, tab3 = st.tabs(["📈 Open Positions", "✅ Closed P&L", "📅 Daily History"])

    # ─── Tab 1: Open Positions ───
    with tab1:
        if positions.empty:
            st.info("No open positions found. Watcher may still be pushing data.")
        else:
            # Colour M2M column
            def style_m2m(val):
                if isinstance(val, (int, float)):
                    return "color: #00d4aa" if val >= 0 else "color: #ff4b6e"
                return ""

            display_cols = [
                "Symbol", "Underlying", "Expiry", "Strike", "Type",
                "Lots", "Avg Price", "LTP", "Open M2M (₹)", "Total P&L (₹)", "Updated At"
            ]
            display_cols = [c for c in display_cols if c in positions.columns]

            styled = (
                positions[display_cols]
                .style
                .map(style_m2m, subset=["Open M2M (₹)", "Total P&L (₹)"])
                .format({
                    "Avg Price": "₹{:.2f}",
                    "LTP":       "₹{:.2f}",
                    "Open M2M (₹)":   "₹{:,.0f}",
                    "Total P&L (₹)":  "₹{:,.0f}",
                    "Strike":    "{:.0f}",
                    "Lots":      "{:.1f}",
                })
            )
            st.dataframe(styled, use_container_width=True, height=400)

            # Per-expiry breakdown
            if "Expiry" in positions.columns:
                st.markdown('<div class="section-header">By Expiry</div>', unsafe_allow_html=True)
                expiry_grp = (
                    positions.groupby("Expiry")
                    .agg({"Open M2M (₹)": "sum", "Total P&L (₹)": "sum", "Symbol": "count"})
                    .rename(columns={"Symbol": "# Contracts"})
                    .reset_index()
                )
                st.dataframe(expiry_grp, use_container_width=True, hide_index=True)

    # ─── Tab 2: Closed P&L ───
    with tab2:
        if closed.empty:
            st.info("No closed positions found yet.")
        else:
            # Group by expiry
            if "Expiry" in closed.columns:
                expiry_opts = ["All"] + sorted(closed["Expiry"].unique().tolist())
                selected    = st.selectbox("Filter by Expiry", expiry_opts)
                if selected != "All":
                    view = closed[closed["Expiry"] == selected]
                else:
                    view = closed
            else:
                view = closed

            def style_realized(val):
                if isinstance(val, (int, float)):
                    return "color: #00d4aa" if val >= 0 else "color: #ff4b6e"
                return ""

            display_cols = [c for c in [
                "Symbol", "Underlying", "Expiry", "Strike", "Type",
                "Buy Qty", "Avg Buy", "Sell Qty", "Avg Sell", "Realized P&L (₹)"
            ] if c in view.columns]

            styled_cl = (
                view[display_cols]
                .style
                .map(style_realized, subset=["Realized P&L (₹)"])
                .format({"Avg Buy": "₹{:.2f}", "Avg Sell": "₹{:.2f}",
                         "Realized P&L (₹)": "₹{:,.0f}", "Strike": "{:.0f}"})
            )
            st.dataframe(styled_cl, use_container_width=True, height=400)

            total_closed_pnl = float(view["Realized P&L (₹)"].sum())
            st.metric(
                "Realized P&L (filtered)",
                fmt_pnl(total_closed_pnl),
                delta=None,
            )

    # ─── Tab 3: Daily history chart ───
    with tab3:
        if daily.empty:
            st.info("No daily P&L history yet. It will appear after the first EOD snapshot.")
        else:
            import plotly.graph_objects as go

            fig = go.Figure()
            fig.add_bar(
                x     = daily["Date"].dt.strftime("%d %b"),
                y     = daily["Total P&L (₹)"],
                marker_color = [
                    "#00d4aa" if v >= 0 else "#ff4b6e"
                    for v in daily["Total P&L (₹)"]
                ],
                name  = "Daily P&L",
            )
            fig.update_layout(
                title       = "Daily P&L",
                plot_bgcolor= "#0e1117",
                paper_bgcolor="#0e1117",
                font_color  = "#c9d1d9",
                xaxis       = dict(gridcolor="#21262d"),
                yaxis       = dict(gridcolor="#21262d", tickprefix="₹"),
                showlegend  = False,
                height      = 400,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Cumulative line
            daily["Cumulative"] = daily["Total P&L (₹)"].cumsum()
            fig2 = go.Figure()
            fig2.add_scatter(
                x    = daily["Date"].dt.strftime("%d %b"),
                y    = daily["Cumulative"],
                mode = "lines+markers",
                line = dict(color="#00d4aa", width=2),
                name = "Cumulative P&L",
            )
            fig2.update_layout(
                title        = "Cumulative P&L",
                plot_bgcolor = "#0e1117",
                paper_bgcolor= "#0e1117",
                font_color   = "#c9d1d9",
                xaxis        = dict(gridcolor="#21262d"),
                yaxis        = dict(gridcolor="#21262d", tickprefix="₹"),
                showlegend   = False,
                height       = 350,
            )
            st.plotly_chart(fig2, use_container_width=True)

            st.dataframe(
                daily[["Date", "Open M2M (₹)", "Realized P&L (₹)", "Total P&L (₹)", "Open Positions"]]
                .assign(Date=daily["Date"].dt.strftime("%d %b %Y"))
                .sort_values("Date", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

    # ── Auto-refresh every 60s ──
    st.markdown("---")
    st.caption("Auto-refreshes every 60 seconds during market hours.")
    time.sleep(60)
    st.rerun()


if __name__ == "__main__":
    main()
