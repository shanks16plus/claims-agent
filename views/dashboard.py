"""Insurer dashboard: what happened to the claims, straight from the claims log (data/runtime/claims.db)."""
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from core import storage
from ui import charts, theme
from ui.theme import band, card, esc, show

CHANNELS = {"form": "Form", "chat": "Chat", "batch": "Batch test"}
PERIODS = {"Last 7 days": 7, "Last 30 days": 30, "All time": None}
FRAUD_LABELS = {
    "ai_content_credentials": "Photo labelled as AI-made",
    "ai_detector_likely": "AI detector: likely generated",
    "ai_detector_possible": "AI detector: possibly generated",
    "duplicate_photo": "Photo seen in an earlier claim",
    "incident_before_policy_start": "Incident before the policy started",
    "editing_software": "Photo saved with editing software",
    "story_photo_mismatch": "Photos don't match the story or the car",
    "incident_in_future": "Incident date in the future",
    "story_photo_partial_mismatch": "Story partly matches the photos",
    "possible_manipulation": "Photo may be edited or generated",
    "no_photo_metadata": "No camera metadata",
    "policy_started_recently": "Policy started days before",
}
STATUS_LABELS = {"settled": "Settled automatically", "awaiting_adjuster": "Waiting for a handler",
                 "adjuster_approved": "Approved by a handler", "adjuster_changed": "Amount changed by a handler",
                 "adjuster_rejected": "Rejected by a handler", "batch_test": "Batch test"}


def duration(seconds):
    if seconds is None or pd.isna(seconds):
        return "-"
    if seconds < 1:
        return "Instant"
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} days"


def euro(value, decimals=2):
    return "-" if value is None or pd.isna(value) else f"€{value:,.{decimals}f}"


def share(part, whole):
    return f"{part / whole:.0%}" if whole else "-"


def load(since, channels):
    claims = storage.list_claims(since=since)
    rows = [{
        "claim_id": c["claim_id"], "filed_at": pd.to_datetime(c["filed_at"]),
        "decided_at": pd.to_datetime(c["decided_at"]) if c["decided_at"] else pd.NaT,
        "channel": CHANNELS.get(c["channel"], c["channel"]), "status": c["status"],
        "outcome": "Settled automatically" if c["decision"] == "auto_settle" else "Sent to a person",
        "estimate_eur": c["estimate_eur"], "payout_eur": c["payout_eur"], "fraud_risk": c["fraud_risk"],
        "fraud_reasons": c["fraud_reasons"] or [], "confidence": c["confidence"], "chat_turns": c["chat_turns"],
        "photo_retakes": c["photo_retakes"], "seconds_to_file": c["seconds_to_file"],
        "processing_seconds": c["processing_seconds"], "api_cost_eur": c["api_cost_eur"],
    } for c in claims]
    df = pd.DataFrame(rows)
    return df[df["channel"].isin(channels)] if len(df) else df


def tile(label, value, note=""):
    note = f"<span>{esc(note)}</span>" if note else ""
    return f"<div class='ca-tile'><p>{esc(label)}</p><b>{esc(value)}</b>{note}</div>"


def table_view(df, key):
    with st.expander("Show as a table"):
        st.dataframe(df, hide_index=True, key=key)


# --- Page -------------------------------------------------------------------------------------------------
with band("paper", "dash-body"):
    log = storage.list_claims()
    seeded = sum(1 for c in log if (c["details"] or {}).get("seeded_from"))
    note = f" ({seeded} from our recorded test runs, 24 to 25 September)" if seeded else ""
    show("<div class='ca-titlebar'><div><div class='ca-label' style='margin:0 0 .5rem'>Insurer</div>"
         "<h1>Dashboard</h1></div><div class='meta'>Updated <b>" + datetime.now().strftime("%H:%M") +
         f"</b> &middot; {len(log)} claims in the log{note}</div></div>")

    # One filter row, above everything it scopes
    with st.container(horizontal=True, gap="medium", key="dash-filters", vertical_alignment="bottom"):
        period = st.segmented_control("Period", list(PERIODS), default="All time", required=True)
        picked = st.segmented_control("Channels", list(CHANNELS.values()), default=list(CHANNELS.values()),
                                      selection_mode="multi")
    days = PERIODS[period]
    since = (date.today() - timedelta(days=days - 1)).isoformat() if days else None
    df = load(since, picked or [])

    if not len(df):
        show("<p class='ca-note'>No claims in this period for these channels yet. File a claim through the form "
             "or the chat, and it appears here.</p>")
        theme.footer(slim=True)
        st.stop()

    total = len(df)
    auto = int((df["outcome"] == "Settled automatically").sum())
    routed = total - auto
    decided = df.dropna(subset=["decided_at"])
    to_decision = (decided["decided_at"] - decided["filed_at"]).dt.total_seconds()
    by_handler = decided[decided["status"].str.startswith("adjuster_")]
    handler_time = (by_handler["decided_at"] - by_handler["filed_at"]).dt.total_seconds()
    decision_note = (f"{len(decided) - len(by_handler)} decided automatically, "
                     + (f"{len(by_handler)} by a handler (median {duration(handler_time.median())})" if len(by_handler)
                        else "none by a handler yet"))
    waiting = df[df["status"] == "awaiting_adjuster"]
    oldest = (datetime.now() - waiting["filed_at"].min()).total_seconds() if len(waiting) else None

    # Hero figure and stat tiles
    show("<div class='ca-kpis' data-reveal='fade'>"
         f"<div class='ca-hero-figure'><p>Settled automatically</p><b>{share(auto, total)}</b>"
         f"<span>{auto} of {total} claims, with no person involved</span></div>"
         "<div class='ca-tiles'>"
         + tile("Claims filed", f"{total:,}", period.lower())
         + tile("Sent to a person", share(routed, total), f"{routed} claim{'' if routed == 1 else 's'}")
         + tile("Time from filing to decision", duration(to_decision.median() if len(to_decision) else None),
                f"median; {decision_note}")
         + tile("Waiting for a handler", f"{len(waiting)}", f"oldest waiting {duration(oldest)}" if oldest else "none")
         + tile("Time to check a claim", duration(df["processing_seconds"].mean()), "average, all model calls")
         + tile("Model cost per claim", euro(df["api_cost_eur"].mean(), 3), f"{euro(df['api_cost_eur'].sum())} in total")
         + "</div></div>")

    # Outcome by channel, and fraud flags by reason
    left, right = st.columns(2, gap="medium")
    with left, card("chart-channel"):
        show("<p class='ca-chart-title'>Outcome by channel</p><p class='ca-small'>Claims per channel, split by what "
             "the rules decided</p>")
        by_channel = df.groupby(["channel", "outcome"]).size().reset_index(name="claims")
        st.altair_chart(charts.stacked_bars(by_channel, "channel", "outcome", "claims", "Claims"), theme=None,
                        width="stretch")
        table_view(by_channel.rename(columns={"channel": "Channel", "outcome": "Outcome", "claims": "Claims"}),
                   "t_channel")
    with right, card("chart-fraud"):
        show("<p class='ca-chart-title'>Fraud flags by reason</p><p class='ca-small'>How often each signal came up. "
             "One claim can have several.</p>")
        flags = df.explode("fraud_reasons").dropna(subset=["fraud_reasons"])
        if len(flags):
            by_reason = (flags["fraud_reasons"].map(lambda code: FRAUD_LABELS.get(code, code))
                         .value_counts().rename_axis("reason").reset_index(name="claims"))
            st.altair_chart(charts.bars(by_reason, "reason", "claims", "Claims"), theme=None, width="stretch")
            table_view(by_reason.rename(columns={"reason": "Reason", "claims": "Claims"}), "t_fraud")
        else:
            show("<p class='ca-note'>No fraud signals in this period.</p>")

    # Claims per day, every day in the period (empty days included)
    with card("chart-days"):
        show("<p class='ca-chart-title'>Claims per day</p><p class='ca-small'>By the day they were filed</p>")
        end = date.today()
        start = date.fromisoformat(since) if since else min(df["filed_at"].dt.date.min(), end - timedelta(days=6))
        per_day = df.assign(day=df["filed_at"].dt.normalize()).groupby(["day", "outcome"]).size().reset_index(name="claims")
        st.altair_chart(charts.daily_columns(per_day, start, end, "outcome", "claims", "Claims"), theme=None,
                        width="stretch")
        table_view(per_day.assign(day=per_day["day"].dt.strftime("%d %b %Y")).rename(
            columns={"day": "Day", "outcome": "Outcome", "claims": "Claims"}), "t_days")

    # The channels side by side
    with card("channels"):
        show("<p class='ca-chart-title'>Channels compared</p>")
        rows = []
        for channel, group in df.groupby("channel"):
            messages = f"{group['chat_turns'].mean():.1f}" if channel == "Chat" else "-"
            settled = (group["outcome"] == "Settled automatically").sum()
            rows.append(f"<tr><td>{esc(channel)}</td><td class='num'>{len(group)}</td>"
                        f"<td class='num'>{share(settled, len(group))}</td><td class='num'>{messages}</td>"
                        f"<td class='num'>{group['photo_retakes'].mean():.1f}</td>"
                        f"<td class='num'>{duration(group['seconds_to_file'].median())}</td>"
                        f"<td class='num'>{duration(group['processing_seconds'].mean())}</td>"
                        f"<td class='num'>{euro(group['api_cost_eur'].mean(), 3)}</td></tr>")
        show("<div class='ca-table-wrap'><table class='ca-table'><thead><tr><th>Channel</th><th class='num'>Claims</th>"
             "<th class='num'>Settled automatically</th><th class='num'>Messages per chat</th>"
             "<th class='num'>Photo retakes</th><th class='num'>Time to file (median)</th>"
             "<th class='num'>Time to check</th><th class='num'>Model cost</th></tr></thead>"
             f"<tbody>{''.join(rows)}</tbody></table></div>")

    # Every claim in the period
    with card("recent"):
        show("<p class='ca-chart-title'>Claims</p><p class='ca-small'>Newest first. Open one to see what the "
             "customer sees (batch tests have no customer page).</p>")
        listing = pd.DataFrame({
            "Claim": df["claim_id"],
            "Filed": df["filed_at"],
            "Channel": df["channel"],
            "Status": df["status"].map(lambda s: STATUS_LABELS.get(s, s)),
            "Estimate": df["estimate_eur"],
            "Payout": df["payout_eur"],
            "Fraud risk": df["fraud_risk"].fillna("-"),
            "Confidence": df["confidence"],
            "Model cost": df["api_cost_eur"],
            "Customer page": ("status?claim=" + df["claim_id"]).where(df["channel"] != "Batch test"),
        })
        st.dataframe(listing, hide_index=True, key="t_claims", placeholder="-", column_config={
            "Customer page": st.column_config.LinkColumn("View", display_text="Open", width="small"),
            "Filed": st.column_config.DatetimeColumn("Filed", format="D MMM, HH:mm"),
            "Estimate": st.column_config.NumberColumn("Estimate", format="euro", width="small"),
            "Payout": st.column_config.NumberColumn("Payout", format="euro", width="small"),
            "Confidence": st.column_config.NumberColumn("Confidence", format="%.2f"),
            "Model cost": st.column_config.NumberColumn("Model cost", format="€%.3f"),
        })

theme.footer(slim=True)
