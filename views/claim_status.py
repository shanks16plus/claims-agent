"""Claim status: both routes (chat and form) land here after filing.
Customers see the decision, the explanation and next steps. Fraud signals and internal checks stay internal."""
from datetime import datetime
from pathlib import Path

import streamlit as st

from core import storage
from core.tools.decide import money
from ui import loaders, theme
from ui.theme import band, card, esc, lift, photo, show

NEXT_STEPS = {
    "paid": ["The amount above is approved.", "You'll get a confirmation with the payment details."],
    "below_deductible": ["Your claim is registered, so there's a record if you need it later.",
                         "If a garage quotes a higher amount, send us the quote and a claims handler "
                         "will look at it again."],
    "review": ["A claims handler has your photos, your answers and our assessment.",
               "They'll contact you about the next steps.",
               "You don't need to send anything else unless they ask."],
}


def header(title, pill=None, filed=None):
    with band("hero-page", "status"):
        theme.hero_media("status")
        theme.heading("Claim status", esc(title), size="page-title", split=True)
        extra = f"<p class='ca-small' style='color:var(--on-dark);margin:.8rem 0 0'>Filed {filed}</p>" if filed else ""
        if pill:
            extra += f"<span class='ca-tag {pill[0]}'>{esc(pill[1])}</span>"
        if extra:
            show(extra)


def lookup_form(message=None):
    with band("paper", "status-body"), lift("status"):
        left, _ = st.columns([13, 8], gap="large")
        with left, card("lookup"):
            if message:
                show(f"<p class='ca-note' style='margin-top:0'>{esc(message)}</p>")
            reference = st.text_input("Claim reference", placeholder="CLM-20260924-3F2A")
            if st.button("Show status", type="primary") and reference.strip():
                st.query_params["claim"] = reference.strip().upper()
                st.rerun()


claim_id = st.query_params.get("claim", "")
record = storage.get_claim(claim_id) if claim_id else None

if not claim_id or record is None:
    header("Check your claim" if not claim_id else "We can't find that claim")
    lookup_form(None if not claim_id else
                f"There's no claim with reference {claim_id}. Check the reference and try again.")
    theme.footer()
    st.stop()

details = record["details"]
claim, decision, estimate = details["claim"], details["decision"], details["estimate"]
language = claim.get("language", "en")
payout = record["payout_eur"] or 0

if record["status"] in ("settled", "adjuster_approved", "adjuster_changed"):
    kind = "paid" if payout > 0 else "below_deductible"
    block = ("settled", "Settled", f"We'll pay {money(payout, language)}") if payout > 0 else \
            ("settled", "Registered", "The repair costs less than your deductible")
    pill = ("settled", "Settled")
else:
    kind = "review"
    block = ("review", "With a claims handler", "A person is reviewing your claim")
    pill = ("review", "With a claims handler")

header(claim_id, pill, datetime.fromisoformat(record["filed_at"]).strftime("%d %B %Y, %H:%M"))

with band("paper", "status-body"), lift("status"):
    main, side = st.columns([13, 8], gap="large")
    with main, card("status"):
        theme.status_block(*block, decision["customer_message"])

        theme.small_heading("What happens next")
        show("<ol class='ca-timeline' data-reveal='stagger' data-delay='0.2'>"
             + "".join(f"<li>{esc(line)}</li>" for line in NEXT_STEPS[kind]) + "</ol>")

        if kind == "paid":
            theme.small_heading("The amount")
            theme.key_values([
                ("Repair estimate, incl. VAT", money(estimate["gross_eur"], language)),
                ("Your deductible", money(estimate["deductible_eur"], language)),
                ("We pay", money(payout, language)),
            ], total=True)

        theme.small_heading("Your claim")
        theme.key_values([
            ("Date", datetime.fromisoformat(claim["incident_date"]).strftime("%d %B %Y")),
            ("Place", claim["incident_place"] or "Not given"),
            ("What happened", claim["what_happened"]),
        ])
        photos = [p for p in claim.get("photos", []) if p.get("usable", True) and Path(p["path"]).exists()]
        if photos:
            theme.small_heading("Your photos")
            figures = "".join(f"<figure><div class='ca-photo'><img alt='' src='{loaders.thumbnail(p['path'], 360)}'>"
                              "</div></figure>" for p in photos)
            show(f"<div class='ca-thumbs'>{figures}</div>")

        show("<div style='height:.6rem'></div>")
        if st.button("File another claim"):
            st.switch_page("views/claim_form.py")
    with side:
        show(photo("workshop" if kind == "review" else "canal_trees", cls="ca-side-photo", parallax=30,
                   tag="A person reviews it" if kind == "review" else "All sorted"))

theme.footer()
