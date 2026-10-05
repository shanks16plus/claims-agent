"""Insurer dashboard: what happened to the claims, straight from the claims log (data/runtime/claims.db)."""
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core import config, storage
from ui import charts, loaders, theme
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
# How a failed rule from core/tools/decide.py reads in the "Why" column
RULE_FAILED = {
    "Policy found": "Policy not found",
    "Policy active": "Policy not active",
    "Own damage covered": "Own damage not covered",
    "Incident date within policy": "Incident date outside the policy",
    "Damage assessment completed": "Damage assessment failed",
    "Damage found in photos": "No damage found in the photos",
    "Fraud check completed": "Fraud check failed",
    "All parts priced": "A damaged part isn't in the price table",
    "Not a possible total loss": "Possible total loss",
}
INSURED_CAR = {"matches": "yes", "different": "no, it looks like a different car", "cannot_tell": "can't tell from the photos"}


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
        "outcome": ("Settled automatically" if c["decision"] == "auto_settle" and c["status"] in ("settled", "batch_test")
                    else "Sent to a person"),
        "estimate_eur": c["estimate_eur"], "payout_eur": c["payout_eur"], "fraud_risk": c["fraud_risk"],
        "fraud_reasons": c["fraud_reasons"] or [], "confidence": c["confidence"], "chat_turns": c["chat_turns"],
        "photo_retakes": c["photo_retakes"], "seconds_to_file": c["seconds_to_file"],
        "processing_seconds": c["processing_seconds"], "api_cost_eur": c["api_cost_eur"],
        "why": why(c["details"], c["status"]), "details": c["details"] or {},
    } for c in claims]
    df = pd.DataFrame(rows)
    return df[df["channel"].isin(channels)] if len(df) else df


def failed_rule(check):
    rule, detail = check["rule"], check.get("detail") or ""
    if rule == "Fraud risk low":
        return f"Fraud risk {detail.removeprefix('Risk: ')}"
    if rule == "Model confidence high":
        return f"Confidence {detail}"
    if rule == "Estimate below auto-settle limit":
        return f"Estimate {detail}"
    if rule == "No out-of-scope situation":
        return detail or "Needs a person"
    return RULE_FAILED.get(rule, rule)


def why(details, status=None):
    """One line on why the rules settled a claim or sent it to a person, from the rule checks stored with it."""
    decision = (details or {}).get("decision") or {}
    if decision.get("decision") == "auto_settle":
        return ("Every rule passed. The customer then asked a person to review it" if status == "awaiting_adjuster"
                else "Every rule passed")
    failed = [check for check in decision.get("checks") or [] if not check["passed"]]
    if not failed:                                    # handed over in the chat, before any assessment
        return "; ".join(decision.get("reasons") or []) or "-"
    hurt = "injury" in ((details.get("claim") or {}).get("scope_flags") or [])
    if hurt and not (details.get("damage") or {}).get("ok"):          # from the stored flag, not from a sentence
        return "Someone may have been hurt: handled by a person, no AI assessment"
    assessed = not any(check["rule"] == "Damage assessment completed" for check in failed)
    return "; ".join(failed_rule(check) for check in failed
                     if assessed or check["rule"] != "Model confidence high")


def tile(label, value, note=""):
    note = f"<span>{esc(note)}</span>" if note else ""
    return f"<div class='ca-tile'><p>{esc(label)}</p><b>{esc(value)}</b>{note}</div>"


def table_view(df, key):
    with st.expander("Show as a table"):
        st.dataframe(df, hide_index=True, key=key)


def table(headers, rows, numeric=(), failed=()):
    """A plain HTML table. Every cell is escaped: the text comes from customers and from the models."""
    num, bad = " class='num'", " class='failed'"
    def cells(tag, values):
        return "".join(f"<{tag}{num if i in numeric else ''}>{esc(v)}</{tag}>" for i, v in enumerate(values))
    body = "".join(f"<tr{bad if n in failed else ''}>{cells('td', row)}</tr>" for n, row in enumerate(rows))
    return (f"<div class='ca-table-wrap'><table class='ca-table'><thead><tr>{cells('th', headers)}</tr></thead>"
            f"<tbody>{body}</tbody></table></div>")


def part_name(part):
    return str(part).replace("_", " ").capitalize()


def yes_no(value):
    return {True: "Yes", False: "No"}.get(value, "-")


def claim_file(row, details):
    """Everything behind one decision: what the customer sent, each rule, the fraud signals and the damage the
    models reported. Read from the claims log, so it also works for claims whose files are gone."""
    claim, decision = details.get("claim") or {}, details.get("decision") or {}
    policy, damage = details.get("policy") or {}, details.get("damage") or {}
    estimate, fraud = details.get("estimate") or {}, details.get("fraud") or {}
    settled = decision.get("decision") == "auto_settle" and row["status"] != "awaiting_adjuster"

    show(f"<p class='ca-file-outcome'><span class='ca-file-tag{' settled' if settled else ''}'>"
         f"{'Settled automatically' if settled else 'Sent to a person'}</span>{esc(row['why'])}</p>"
         + ("" if settled or decision.get("decision") == "auto_settle" or not decision.get("next_step") else
            f"<p class='ca-small'>Suggested next step for the handler: {esc(decision['next_step'])}</p>"))

    for request in storage.list_overrides(row.name):
        if request["action"] == "review_requested":
            show("<p class='ca-note'>The customer asked for a person to review the automatic decision"
                 + (f" (it was a payout of {euro(request['amount_before'])})" if request["amount_before"] else "")
                 + (f". Their explanation: {esc(request['note'])}" if request["note"] else ". No explanation given.")
                 + "</p>")

    turns = [t for t in (details.get("handover") or {}).get("conversation") or [] if t.get("text")]
    if turns:                                         # a chat handover: the conversation is all there is
        theme.small_heading("The conversation")
        show(table(["Who", "Said"], [("Customer" if t.get("role") == "customer" else "AI assistant", t["text"])
                                     for t in turns]))

    left, right = st.columns(2, gap="large")
    with left:
        theme.small_heading("What the customer sent")
        on_policy = "Policy not found"
        if policy.get("found"):
            on_policy = policy.get("vehicle", "-") + (f", registration {policy['registration']}"
                                                      if policy.get("registration") else "")
        theme.key_values([
            ("Policy", claim.get("policy_number") or "-"),
            ("Car on the policy", on_policy if policy else "-"),
            ("Incident", ", ".join(str(v) for v in (claim.get("incident_date"), claim.get("incident_place")) if v) or "-"),
            ("What happened", claim.get("what_happened") or "-"),
            ("Another car involved", yes_no(claim.get("other_party_involved"))),
            ("Car still drivable", yes_no(claim.get("drivable"))),
        ])
        photos = [p for p in claim.get("photos") or [] if p.get("path") and Path(p["path"]).exists()]
        if photos:
            figures = "".join(f"<figure><div class='ca-photo'><img alt='' src='{loaders.thumbnail(p['path'], 360)}'>"
                              f"</div><figcaption>{esc(config.PHOTO_SLOTS.get(p.get('slot'), 'Photo'))}</figcaption>"
                              "</figure>" for p in photos)
            show(f"<div class='ca-thumbs' style='margin-top:1.2rem'>{figures}</div>")
        elif claim.get("photos"):
            show(f"<p class='ca-small' style='margin-top:1rem'>{len(claim['photos'])} photos were sent. The files "
                 "are no longer on this server.</p>")
    with right:
        theme.small_heading("The rules")
        checks = decision.get("checks") or []
        if checks:
            show("<p class='ca-small'>A claim is settled automatically only when every rule passes. One failed "
                 "rule sends it to a person.</p>"
                 + table(["Rule", "Result", "Detail"],
                         [(c["rule"], "Passed" if c["passed"] else "Failed", c.get("detail") or "") for c in checks],
                         failed=[n for n, c in enumerate(checks) if not c["passed"]]))
        else:
            reasons = "; ".join(decision.get("reasons") or []) or "No rules were run"
            show(f"<p class='ca-small'>{esc(reasons)}. The assessment didn't run, so there are no rule results.</p>")

    if fraud:
        theme.small_heading(f"Fraud check: {fraud.get('risk', '-')} risk, {fraud.get('points', 0)} points")
        show(f"<p class='ca-small'>Each signal adds points. {config.FRAUD_MEDIUM} or more is medium risk, "
             f"{config.FRAUD_HIGH} or more is high. Only low risk can be settled automatically.</p>")
        signals = fraud.get("signals") or []
        if signals:
            show(table(["Signal", "Points", "What was found"],
                       [(FRAUD_LABELS.get(s["code"], s["code"]), f"+{s['points']}", s.get("detail") or "")
                        for s in signals], numeric=(1,)))
        else:
            show("<p class='ca-note' style='margin-top:.6rem'>No fraud signals.</p>")
        review = fraud.get("review") or {}
        if "insured_car" in review:
            show("<p class='ca-small' style='margin-top:.8rem'>Plate the AI read in the photos: "
                 f"<b>{esc(review.get('plate_in_photos') or 'none readable')}</b>. Is it the car on the policy: "
                 f"<b>{esc(INSURED_CAR.get(review['insured_car'], review['insured_car']))}</b>.</p>")

    if damage:
        confidence = damage.get("confidence")
        theme.small_heading("Damage and price")
        note = f"Confidence {confidence:.2f} (needs {config.MIN_CONFIDENCE_AUTO:.2f}). " if confidence is not None else ""
        if damage.get("looks"):
            note += (f"Assessed three times because the first estimate was close to the limit: "
                     f"{', '.join(euro(e) for e in damage['looks'])}. The middle one is used. ")
        show(f"<p class='ca-small'>{esc(note + (damage.get('confidence_reason') or damage.get('error') or ''))}</p>")
        parts = damage.get("damaged_parts") or []
        if parts:
            show(table(["Part", "Severity", "Repair or replace", "Mentioned by customer", "What the AI saw"],
                       [(part_name(p["part"]), p["severity"], p.get("action", "-"),
                         yes_no(p.get("mentioned_by_customer")), p.get("evidence") or "") for p in parts]))
        if estimate:
            theme.key_values([
                ("Parts, paint and labour", euro(estimate.get("subtotal_ex_vat_eur"))),
                ("VAT", euro(estimate.get("vat_eur"))),
                ("Estimate", euro(estimate.get("gross_eur"))),
                ("Deductible", euro(estimate.get("deductible_eur"))),
                ("Paid" if settled else "After the deductible (not paid, waiting for a person)",
                 euro(estimate.get("payout_eur"))),
            ], total=True)


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
        show("<p class='ca-chart-title'>Outcome by channel</p><p class='ca-small'>Claims per channel, split by "
             "outcome</p>")
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
        show("<p class='ca-chart-title'>Claims</p><p class='ca-small'>Newest first. The Why column says which "
             "rules sent a claim to a person. Open shows what the customer sees (batch tests have no customer "
             "page).</p>")
        listing = pd.DataFrame({
            "Claim": df["claim_id"],
            "Filed": df["filed_at"],
            "Channel": df["channel"],
            "Status": df["status"].map(lambda s: STATUS_LABELS.get(s, s)),
            "Why": df["why"],
            "Estimate": df["estimate_eur"],
            "Payout": df["payout_eur"],
            "Fraud risk": df["fraud_risk"].fillna("-"),
            "Confidence": df["confidence"],
            "Model cost": df["api_cost_eur"],
            "Customer page": ("status?claim=" + df["claim_id"]).where(df["channel"] != "Batch test"),
        })
        st.dataframe(listing, hide_index=True, key="t_claims", placeholder="-", column_config={
            "Customer page": st.column_config.LinkColumn("View", display_text="Open", width="small"),
            "Why": st.column_config.TextColumn("Why", width="large"),
            "Filed": st.column_config.DatetimeColumn("Filed", format="D MMM, HH:mm"),
            "Estimate": st.column_config.NumberColumn("Estimate", format="euro"),
            "Payout": st.column_config.NumberColumn("Payout", format="euro"),
            "Confidence": st.column_config.NumberColumn("Confidence", format="%.2f"),
            "Model cost": st.column_config.NumberColumn("Model cost", format="€%.3f"),
        })

    # One claim in full: the answer to "why wasn't this one settled?"
    with card("claim-file"):
        show("<p class='ca-chart-title'>Claim file</p><p class='ca-small'>Pick a claim to see every rule, the "
             "fraud signals and the damage the AI reported. This is what a claims handler works from.</p>")
        rows = df.set_index("claim_id")
        chosen = st.selectbox(
            "Claim", list(rows.index), key="claim_file",
            format_func=lambda cid: f"{cid}  ·  {rows.loc[cid, 'filed_at']:%-d %b, %H:%M}  ·  "
                                    f"{rows.loc[cid, 'channel']}  ·  {STATUS_LABELS.get(rows.loc[cid, 'status'])}")
        claim_file(rows.loc[chosen], rows.loc[chosen, "details"])

theme.footer(slim=True)
