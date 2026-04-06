"""
Member Intelligence Dashboard
Run: streamlit run dashboard/app.py
Requires the FastAPI server running on localhost:8000.
"""
from __future__ import annotations

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

API_BASE = "http://localhost:8000"
TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Member Intelligence",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "current_page" not in st.session_state:
    st.session_state.current_page = "Member Search"
if "selected_member_id" not in st.session_state:
    st.session_state.selected_member_id = None
if "ai_insight" not in st.session_state:
    st.session_state.ai_insight = None
if "ai_insight_member_id" not in st.session_state:
    st.session_state.ai_insight_member_id = None


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def _get(path: str, **params) -> dict | list | None:
    try:
        r = httpx.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except httpx.RequestError as e:
        st.error(f"Could not reach API at {API_BASE} — is the server running? ({e})")
        return None


def _post(path: str) -> dict | None:
    try:
        r = httpx.post(f"{API_BASE}{path}", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except httpx.RequestError as e:
        st.error(f"Could not reach API at {API_BASE} — is the server running? ({e})")
        return None


@st.cache_data(ttl=60, show_spinner="Loading members…")
def fetch_all_members() -> list[dict]:
    """Page through the full member list and return all records."""
    all_members: list[dict] = []
    page = 1
    while True:
        data = _get("/members", page=page, page_size=100)
        if not data:
            break
        results = data.get("results", [])
        all_members.extend(results)
        if page >= data.get("pages", 1):
            break
        page += 1
    return all_members


@st.cache_data(ttl=30, show_spinner="Loading member…")
def fetch_member(member_id: int) -> dict | None:
    return _get(f"/members/{member_id}")


@st.cache_data(ttl=30, show_spinner="Loading portfolio…")
def fetch_portfolio(member_id: int) -> dict | None:
    return _get(f"/members/{member_id}/portfolio")


@st.cache_data(ttl=120, show_spinner="Loading segment data…")
def fetch_segments() -> dict | None:
    return _get("/segments/summary")


def post_analyze(member_id: int) -> dict | None:
    """Always fresh — do not cache AI calls."""
    return _post(f"/members/{member_id}/analyze")


# ---------------------------------------------------------------------------
# Navigation sidebar
# ---------------------------------------------------------------------------
PAGES = ["Member Search", "Member Detail", "Segment Summary"]

with st.sidebar:
    st.title("🏦 Member Intel")
    st.divider()
    page = st.radio(
        "Navigate",
        PAGES,
        index=PAGES.index(st.session_state.current_page),
        label_visibility="collapsed",
    )
    st.session_state.current_page = page

    if st.session_state.selected_member_id and page == "Member Detail":
        st.caption(f"Viewing member ID {st.session_state.selected_member_id}")

    st.divider()
    if st.button("Clear cache", use_container_width=True):
        st.cache_data.clear()
        st.session_state.ai_insight = None
        st.session_state.ai_insight_member_id = None
        st.rerun()


# ---------------------------------------------------------------------------
# Page 1 — Member Search
# ---------------------------------------------------------------------------
def page_member_search() -> None:
    st.header("Member Search")

    query = st.text_input(
        "Search by name or member number",
        placeholder="e.g. Smith  or  MBR00042",
    ).strip().lower()

    segment_filter = st.selectbox(
        "Filter by segment",
        options=["All", "premium", "standard", "basic"],
        index=0,
    )

    all_members = fetch_all_members()
    if not all_members:
        st.warning("No members loaded — check the API connection.")
        return

    df = pd.DataFrame(all_members)

    # Apply segment filter
    if segment_filter != "All":
        df = df[df["segment"] == segment_filter]

    # Apply text filter across name columns and member_number
    if query:
        mask = (
            df["first_name"].str.lower().str.contains(query, na=False)
            | df["last_name"].str.lower().str.contains(query, na=False)
            | (df["first_name"].str.lower() + " " + df["last_name"].str.lower()).str.contains(query, na=False)
            | df["member_number"].str.lower().str.contains(query, na=False)
        )
        df = df[mask]

    st.caption(f"{len(df)} member(s) found")

    if df.empty:
        st.info("No members match your search.")
        return

    display_cols = ["id", "member_number", "first_name", "last_name",
                    "email", "segment", "member_since", "zip_code"]
    display_df = df[display_cols].reset_index(drop=True)

    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "member_number": st.column_config.TextColumn("Member #"),
            "first_name": st.column_config.TextColumn("First Name"),
            "last_name": st.column_config.TextColumn("Last Name"),
            "email": st.column_config.TextColumn("Email"),
            "segment": st.column_config.TextColumn("Segment"),
            "member_since": st.column_config.TextColumn("Member Since"),
            "zip_code": st.column_config.TextColumn("ZIP"),
        },
    )

    selected_rows = event.selection.rows
    if selected_rows:
        selected_id = int(display_df.iloc[selected_rows[0]]["id"])
        col1, col2 = st.columns([2, 6])
        with col1:
            if st.button("View Details →", type="primary", use_container_width=True):
                st.session_state.selected_member_id = selected_id
                st.session_state.ai_insight = None
                st.session_state.ai_insight_member_id = None
                st.session_state.current_page = "Member Detail"
                st.rerun()
        with col2:
            name = f"{display_df.iloc[selected_rows[0]]['first_name']} {display_df.iloc[selected_rows[0]]['last_name']}"
            st.caption(f"Selected: **{name}** (ID {selected_id})")


# ---------------------------------------------------------------------------
# Page 2 — Member Detail
# ---------------------------------------------------------------------------
def _ratio_color(ratio: float | None) -> str:
    if ratio is None:
        return "gray"
    if ratio > 0.8:
        return "red"
    if ratio > 0.5:
        return "orange"
    return "green"


def page_member_detail() -> None:
    st.header("Member Detail")

    member_id = st.session_state.selected_member_id

    if member_id is None:
        st.info("No member selected. Go to **Member Search** and click View Details.")
        return

    member = fetch_member(member_id)
    portfolio = fetch_portfolio(member_id)

    if not member or not portfolio:
        return

    # -- Header row ----------------------------------------------------------
    col_name, col_num, col_seg, col_since, col_tenure = st.columns(5)
    col_name.metric("Name", f"{member['first_name']} {member['last_name']}")
    col_num.metric("Member #", member["member_number"])
    col_seg.metric("Segment", (member.get("segment") or "—").title())
    col_since.metric("Member Since", member["member_since"])
    col_tenure.metric("Tenure", f"{member['summary']['tenure_years']} yrs")

    st.divider()

    # -- Key ratios ----------------------------------------------------------
    st.subheader("Portfolio Summary")
    total_dep = float(portfolio["total_deposits"])
    total_loan = float(portfolio["total_loan_balance"])
    net_worth = float(portfolio["net_worth"])
    ltd = portfolio.get("loan_to_deposit_ratio")
    ltd_float = float(ltd) if ltd is not None else None

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Deposits", f"${total_dep:,.2f}")
    k2.metric("Total Loan Balance", f"${total_loan:,.2f}")
    k3.metric("Net Worth", f"${net_worth:,.2f}")
    k4.metric(
        "Loan-to-Deposit Ratio",
        f"{ltd_float:.2%}" if ltd_float is not None else "N/A",
    )

    st.divider()

    # -- Accounts table ------------------------------------------------------
    col_acct, col_loan = st.columns(2)

    with col_acct:
        st.subheader(f"Accounts ({len(portfolio['accounts'])})")
        if portfolio["accounts"]:
            acct_df = pd.DataFrame(portfolio["accounts"])[
                ["account_type", "balance", "opened_date", "status"]
            ]
            acct_df["balance"] = acct_df["balance"].apply(lambda v: f"${float(v):,.2f}")
            acct_df.columns = ["Type", "Balance", "Opened", "Status"]
            st.dataframe(acct_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No accounts on file.")

    # -- Loans table ---------------------------------------------------------
    with col_loan:
        st.subheader(f"Loans ({len(portfolio['loans'])})")
        if portfolio["loans"]:
            loan_df = pd.DataFrame(portfolio["loans"])[
                ["loan_type", "current_balance", "interest_rate", "maturity_date", "status"]
            ]
            loan_df["current_balance"] = loan_df["current_balance"].apply(lambda v: f"${float(v):,.2f}")
            loan_df["interest_rate"] = loan_df["interest_rate"].apply(lambda v: f"{float(v):.2%}")
            loan_df.columns = ["Type", "Balance", "Rate", "Matures", "Status"]
            st.dataframe(loan_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No loans on file.")

    st.divider()

    # -- AI Insight ----------------------------------------------------------
    st.subheader("AI Member Insight")

    # Invalidate cached insight when member changes
    if st.session_state.ai_insight_member_id != member_id:
        st.session_state.ai_insight = None
        st.session_state.ai_insight_member_id = member_id

    if st.session_state.ai_insight is None:
        if st.button("Analyze with AI", type="primary", icon="✨"):
            with st.spinner("Generating insight with Claude…"):
                result = post_analyze(member_id)
            if result:
                st.session_state.ai_insight = result
                st.rerun()
    else:
        insight = st.session_state.ai_insight

        st.markdown(f"*Generated at {insight['generated_at']}*")

        st.markdown("**Narrative**")
        st.markdown(insight["narrative"])

        col_risk, col_cross = st.columns(2)

        with col_risk:
            st.markdown("**Risk Flags**")
            if insight["risk_flags"]:
                for flag in insight["risk_flags"]:
                    st.warning(flag, icon="⚠️")
            else:
                st.success("No material risk flags.", icon="✅")

        with col_cross:
            st.markdown("**Cross-Sell Opportunities**")
            if insight["cross_sell_opportunities"]:
                for opp in insight["cross_sell_opportunities"]:
                    st.info(opp, icon="💡")
            else:
                st.caption("No specific opportunities identified.")

        if st.button("Re-analyze", icon="🔄"):
            st.session_state.ai_insight = None
            st.rerun()


# ---------------------------------------------------------------------------
# Page 3 — Segment Summary
# ---------------------------------------------------------------------------
def page_segment_summary() -> None:
    st.header("Segment Summary")

    data = fetch_segments()
    if not data or not data.get("segments"):
        st.warning("No segment data available.")
        return

    segments = data["segments"]
    df = pd.DataFrame(segments)

    # Cast numeric columns
    for col in ("avg_deposits", "avg_loan_balance", "avg_loan_to_deposit_ratio"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # -- KPI strip -----------------------------------------------------------
    st.subheader("Overview")
    cols = st.columns(len(df))
    for col, row in zip(cols, df.itertuples()):
        with col:
            st.metric(row.segment.title(), f"{row.member_count} members")
            st.caption(f"Avg deposits: ${row.avg_deposits:,.0f}")
            st.caption(f"Avg loans: ${row.avg_loan_balance:,.0f}")
            ltd = row.avg_loan_to_deposit_ratio
            st.caption(f"Avg LTD: {ltd:.2%}" if ltd is not None and not pd.isna(ltd) else "Avg LTD: N/A")

    st.divider()

    # -- Bar charts ----------------------------------------------------------
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Avg Deposits by Segment")
        fig_dep = px.bar(
            df.sort_values("avg_deposits", ascending=False),
            x="segment",
            y="avg_deposits",
            color="segment",
            color_discrete_sequence=px.colors.qualitative.Set2,
            labels={"segment": "Segment", "avg_deposits": "Avg Deposits ($)"},
            text_auto=".2s",
        )
        fig_dep.update_layout(showlegend=False, yaxis_tickprefix="$", yaxis_tickformat=",.0f")
        fig_dep.update_traces(textposition="outside")
        st.plotly_chart(fig_dep, use_container_width=True)

    with chart_col2:
        st.subheader("Avg Loan Balance by Segment")
        fig_loan = px.bar(
            df.sort_values("avg_loan_balance", ascending=False),
            x="segment",
            y="avg_loan_balance",
            color="segment",
            color_discrete_sequence=px.colors.qualitative.Set2,
            labels={"segment": "Segment", "avg_loan_balance": "Avg Loan Balance ($)"},
            text_auto=".2s",
        )
        fig_loan.update_layout(showlegend=False, yaxis_tickprefix="$", yaxis_tickformat=",.0f")
        fig_loan.update_traces(textposition="outside")
        st.plotly_chart(fig_loan, use_container_width=True)

    # -- LTD ratio chart -----------------------------------------------------
    st.subheader("Avg Loan-to-Deposit Ratio by Segment")
    ltd_df = df.dropna(subset=["avg_loan_to_deposit_ratio"])
    if not ltd_df.empty:
        fig_ltd = px.bar(
            ltd_df.sort_values("avg_loan_to_deposit_ratio", ascending=False),
            x="segment",
            y="avg_loan_to_deposit_ratio",
            color="segment",
            color_discrete_sequence=px.colors.qualitative.Pastel,
            labels={"segment": "Segment", "avg_loan_to_deposit_ratio": "Avg LTD Ratio"},
            text_auto=".2%",
        )
        fig_ltd.update_layout(showlegend=False, yaxis_tickformat=".0%")
        fig_ltd.update_traces(texttemplate="%{y:.1%}", textposition="outside")
        st.plotly_chart(fig_ltd, use_container_width=True)

    # -- Top loan type table -------------------------------------------------
    st.subheader("Top Loan Type by Segment")
    top_df = df[["segment", "top_loan_type", "member_count"]].copy()
    top_df.columns = ["Segment", "Top Loan Type", "Members"]
    top_df["Segment"] = top_df["Segment"].str.title()
    top_df["Top Loan Type"] = top_df["Top Loan Type"].fillna("—").str.title()
    st.dataframe(top_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if st.session_state.current_page == "Member Search":
    page_member_search()
elif st.session_state.current_page == "Member Detail":
    page_member_detail()
elif st.session_state.current_page == "Segment Summary":
    page_segment_summary()
