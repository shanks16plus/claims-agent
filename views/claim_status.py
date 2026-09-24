"""Claim status: both routes (chat and form) land here after filing.
Customers see the decision, the explanation and next steps. Fraud signals and internal checks stay internal."""
from datetime import datetime

import streamlit as st

from core import config, storage
from core.tools.decide import money
from ui import theme

NEXT_STEPS = {
    "paid": ["The amount above is approved.", "You'll get a confirmation with the payment details."],
    "below_deductible": ["Your claim is registered, so there's a record if you need it later.",
                         "If a garage quotes a higher amount, send us the quote and a claims handler "
                         "will look at it again."],
    "review": ["A claims handler has your photos, your answers and our assessment.",
               "They'll contact you about the next steps.",
               "You don't need to send anything else unless they ask."],
}

claim_id = st.query_params.get("claim", "")
theme.eyebrow("Claim status")

if not claim_id:
    st.markdown("# Check your claim")
    reference = st.text_input("Claim reference", placeholder="CLM-20260924-3F2A")
    if st.button("Show status", type="primary") and reference.strip():
        st.query_params["claim"] = reference.strip().upper()
        st.rerun()
    theme.footer()
    st.stop()

record = storage.get_claim(claim_id)
if record is None:
    st.markdown("# We can't find that claim")
    st.markdown(f"<p class='ca-lede'>There's no claim with reference {claim_id}. Check the reference and try "
                "again.</p>", unsafe_allow_html=True)
    if st.button("Try another reference"):
        st.query_params.clear()
        st.rerun()
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
else:
    kind = "review"
    block = ("review", "With a claims handler", "A person is reviewing your claim")

main, _, side = st.columns([12, 1, 8])
with main:
    st.markdown(f"# {claim_id}")
    filed = datetime.fromisoformat(record["filed_at"]).strftime("%d %B %Y, %H:%M")
    st.markdown(f"<p class='ca-small' style='margin-top:-0.6rem'>Filed {filed}</p>", unsafe_allow_html=True)
    theme.status_block(block[0], block[1], block[2], decision["customer_message"])

    st.markdown("### What happens next")
    st.markdown("\n".join(f"- {line}" for line in NEXT_STEPS[kind]))

    if kind == "paid":
        st.markdown("### The amount")
        theme.key_values([
            ("Repair estimate, incl. VAT", money(estimate["gross_eur"], language)),
            ("Your deductible", money(estimate["deductible_eur"], language)),
            ("We pay", money(payout, language)),
        ])

    st.markdown("### Your claim")
    theme.key_values([
        ("Date", datetime.fromisoformat(claim["incident_date"]).strftime("%d %B %Y")),
        ("Place", claim["incident_place"] or "Not given"),
        ("What happened", claim["what_happened"]),
    ])
    photos = [p for p in claim.get("photos", []) if p.get("usable", True)]
    if photos:
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.image([p["path"] for p in photos], caption=[config.PHOTO_SLOTS[p["slot"]] for p in photos], width=150)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    if st.button("File another claim"):
        st.switch_page("views/claim_form.py")

with side:
    theme.photo("status", height=640, crop="center")

theme.footer()
