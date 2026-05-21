"""
streamlit_app.py  —  Positional Portfolio Dashboard
Reads from Google Sheets, displays live M2M.
"""

import json
import time
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta

st.set_page_config(
    page_title="Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  .stApp { background-color: #0e1117; }
  .metric-card {
    background: #1c1f26; border-radius: 12px;
    padding: 18px 24px; border-left: 4px solid #00d4aa; margin-bottom: 8px;
  }
  .metric-label { color: #8b8fa8; font-size: 13px; font-weight: 500; }
  .metric-value { font-size: 28px; font-weight: 700; margin-top: 4px; }
  .positive { color: #00d4aa; }
  .negative { color: #ff4b6e; }
  .neutral  { color: #c9d1d9; }
  .section-header {
    color: #8b8fa8; font-size: 12px; font-weight: 600;
    letter-spacing: 1.5px; text-transform: uppercase;
    margin: 24px 0 8px; border-bottom: 1px solid #21262d; padding-bottom: 6px;
  }
</style>
""", unsafe_allow_html=True)


# ── Google Sheets ─────────────────────────────────────────────────────────────

@st.cache_resource
def _get_sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    try:
        info = json.loads(st.secrets["gsheet"]["credentials_json"])
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        sid   = st.secrets["gsheet"]["spreadsheet_id"]
    except Exception:
        import os
        creds = Credentials.from_service_account_file(
            os.environ.get("GSHEET_CREDS", "gsheet_credentials.json"), scopes=scopes)
        sid = os.environ.get("SPREADSHEET_ID", "")
    return gspread.authorize(creds).open_by_key(sid)


@st.cache_data(ttl=55)
def read_tab(name: str) -> pd.DataFrame:
    try:
        ws   = _get_sheet().worksheet(name)
        rows = ws.get_all_values()
        if not rows or len(rows) < 2:
            return pd.DataFrame()
        return pd.DataFrame(rows[1:], columns=rows[0])
    except Exception as e:
        st.warning(f"Could not load {name}: {e}")
        return pd.DataFrame()


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str).str.replace(",", "").str.strip(), errors="coerce"
    ).fillna(0.0)


def load_positions() -> pd.DataFrame:
    df = read_tab("Positions")
    if df.empty:
        return df
    df = df[df["Symbol"].str.strip().ne("") & df["Symbol"].ne("TOTAL")].copy()
    for c in ["Lots","Net Qty","Avg Price","LTP","Open M2M (₹)","Realized P&L (₹)","Total P&L (₹)"]:
        if c in df.columns:
            df[c] = to_num(df[c])
    if "Strike" in df.columns:
        df["Strike"] = to_num(df["Strike"])
    return df


def load_closed() -> pd.DataFrame:
    df = read_tab("ClosedPnL")
    if df.empty:
        return df
    df = df[
        df["Symbol"].str.strip().ne("") &
        ~df["Symbol"].str.startswith("──") &
        df["Symbol"].ne("GRAND TOTAL")
    ].copy()
    for c in ["Realized P&L (₹)","Avg Buy","Avg Sell","Buy Qty","Sell Qty"]:
        if c in df.columns:
            df[c] = to_num(df[c])
    return df


def load_daily() -> pd.DataFrame:
    df = read_tab("DailyPnL")
    if df.empty:
        return df
    df = df.copy()
    for c in ["Open M2M (₹)","Realized P&L (₹)","Total P&L (₹)"]:
        if c in df.columns:
            df[c] = to_num(df[c])
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).sort_values("Date")
    return df


def cum_pnl(daily: pd.DataFrame) -> dict:
    if daily.empty:
        return {k: 0.0 for k in ["today","week","month","quarter","year"]}
    today = date.today()
    col   = "Total P&L (₹)"
    def since(d):
        return float(daily.loc[daily["Date"].dt.date >= d, col].sum())
    qm = ((today.month - 1) // 3) * 3 + 1
    return {
        "today":   since(today),
        "week":    since(today - timedelta(days=today.weekday())),
        "month":   since(today.replace(day=1)),
        "quarter": since(today.replace(month=qm, day=1)),
        "year":    since(today.replace(month=1, day=1)),
    }


def fmt(v: float) -> str:
    sign = "+" if v > 0 else ""
    return f"{sign}₹{v:,.0f}"


def css(v: float) -> str:
    return "positive" if v >= 0 else "negative"


def card(label, value, cls="neutral"):
    st.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value {cls}">{value}</div>'
        f'</div>', unsafe_allow_html=True)


# ── Column config helpers (no Styler, no formatting bugs) ─────────────────────

INR0 = st.column_config.NumberColumn()
INR2 = st.column_config.NumberColumn()
NUM1 = st.column_config.NumberColumn()
NUM0 = st.column_config.NumberColumn()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ct, cr = st.columns([5, 1])
    with ct:
        st.markdown("## 📊 Positional Portfolio")
        st.caption(f"Last loaded: {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
    with cr:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("Loading …"):
        positions = load_positions()
        closed    = load_closed()
        daily     = load_daily()

    open_m2m      = float(positions["Open M2M (₹)"].sum())     if not positions.empty else 0.0
    real_open     = float(positions["Realized P&L (₹)"].sum()) if not positions.empty else 0.0
    real_cl       = float(closed["Realized P&L (₹)"].sum())    if not closed.empty    else 0.0
    total_real    = real_open + real_cl
    total_pnl     = open_m2m + total_real
    cp            = cum_pnl(daily)

    st.markdown('<div class="section-header">Portfolio Overview</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: card("Open M2M",      fmt(open_m2m),   css(open_m2m))
    with c2: card("Realized P&L",  fmt(total_real),  css(total_real))
    with c3: card("Net Total P&L", fmt(total_pnl),   css(total_pnl))
    with c4: card("Open Positions", str(len(positions)), "neutral")

    st.markdown('<div class="section-header">Cumulative P&L</div>', unsafe_allow_html=True)
    w1, w2, w3, w4, w5 = st.columns(5)
    for w, lbl, k in [(w1,"Today","today"),(w2,"Week","week"),(w3,"Month","month"),
                       (w4,"Quarter","quarter"),(w5,"Year","year")]:
        with w:
            v = cp[k]
            card(lbl, fmt(v), css(v))

    tab1, tab2, tab3 = st.tabs(["📈 Open Positions", "✅ Closed P&L", "📅 Daily History"])

    # ── Open Positions ────────────────────────────────────────────────────────
    with tab1:
        if positions.empty:
            st.info("No open positions found.")
        else:
            cols = [c for c in ["Symbol","Underlying","Expiry","Strike","Type",
                                 "Lots","Avg Price","LTP","Open M2M (₹)","Total P&L (₹)","Updated At"]
                    if c in positions.columns]
            st.dataframe(
                positions[cols],
                use_container_width=True,
                height=420,
                hide_index=True,
                column_config={
                    "Avg Price":     INR2,
                    "LTP":           INR2,
                    "Open M2M (₹)":  INR0,
                    "Total P&L (₹)": INR0,
                    "Strike":        NUM0,
                    "Lots":          NUM1,
                },
            )

            if "Expiry" in positions.columns:
                st.markdown('<div class="section-header">By Expiry</div>', unsafe_allow_html=True)
                eg = (positions.groupby("Expiry")
                      .agg({"Open M2M (₹)":"sum","Total P&L (₹)":"sum","Symbol":"count"})
                      .rename(columns={"Symbol":"Contracts"})
                      .reset_index())
                st.dataframe(
                    eg, use_container_width=True, hide_index=True,
                    column_config={"Open M2M (₹)": INR0, "Total P&L (₹)": INR0},
                )

    # ── Closed P&L ────────────────────────────────────────────────────────────
    with tab2:
        if closed.empty:
            st.info("No closed positions yet.")
        else:
            if "Expiry" in closed.columns:
                opts = ["All"] + sorted(closed["Expiry"].dropna().unique().tolist())
                sel  = st.selectbox("Filter by Expiry", opts)
                view = closed if sel == "All" else closed[closed["Expiry"] == sel]
            else:
                view = closed

            cols2 = [c for c in ["Symbol","Underlying","Expiry","Strike","Type",
                                   "Buy Qty","Avg Buy","Sell Qty","Avg Sell","Realized P&L (₹)"]
                     if c in view.columns]
            st.dataframe(
                view[cols2],
                use_container_width=True,
                height=420,
                hide_index=True,
                column_config={
                    "Avg Buy":          INR2,
                    "Avg Sell":         INR2,
                    "Realized P&L (₹)": INR0,
                },
            )
            st.metric("Realized P&L (filtered)", fmt(float(view["Realized P&L (₹)"].sum())))

    # ── Daily History ─────────────────────────────────────────────────────────
    with tab3:
        if daily.empty:
            st.info("No daily P&L history yet. Appears after first EOD snapshot at 15:35.")
        else:
            import plotly.graph_objects as go

            fig = go.Figure(go.Bar(
                x=daily["Date"].dt.strftime("%d %b"),
                y=daily["Total P&L (₹)"],
                marker_color=["#00d4aa" if v >= 0 else "#ff4b6e" for v in daily["Total P&L (₹)"]],
            ))
            fig.update_layout(title="Daily P&L", plot_bgcolor="#0e1117",
                paper_bgcolor="#0e1117", font_color="#c9d1d9", height=400,
                xaxis=dict(gridcolor="#21262d"),
                yaxis=dict(gridcolor="#21262d", tickprefix="₹"), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            daily2 = daily.copy()
            daily2["Cumulative"] = daily2["Total P&L (₹)"].cumsum()
            fig2 = go.Figure(go.Scatter(
                x=daily2["Date"].dt.strftime("%d %b"), y=daily2["Cumulative"],
                mode="lines+markers", line=dict(color="#00d4aa", width=2),
            ))
            fig2.update_layout(title="Cumulative P&L", plot_bgcolor="#0e1117",
                paper_bgcolor="#0e1117", font_color="#c9d1d9", height=350,
                xaxis=dict(gridcolor="#21262d"),
                yaxis=dict(gridcolor="#21262d", tickprefix="₹"), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

            hist = daily[["Date","Open M2M (₹)","Realized P&L (₹)","Total P&L (₹)","Open Positions"]].copy()
            hist["Date"] = hist["Date"].dt.strftime("%d %b %Y")
            st.dataframe(hist.sort_values("Date", ascending=False),
                         use_container_width=True, hide_index=True,
                         column_config={"Open M2M (₹)": INR0,
                                        "Realized P&L (₹)": INR0,
                                        "Total P&L (₹)": INR0})

    st.markdown("---")
    st.caption("Auto-refreshes every 60 seconds.")
    time.sleep(60)
    st.rerun()


if __name__ == "__main__":
    main()
