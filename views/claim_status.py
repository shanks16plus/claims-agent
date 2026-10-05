"""Claim status: both routes (chat and form) land here after filing.
Customers see the decision, how it was made (AI, fixed rules or a person) and the next steps. Fraud signals and
internal checks stay internal."""
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
                         "If a garage quotes a higher amount, ask for a review above and tell the claims handler "
                         "about the quote."],
    "review": ["A claims handler has your photos, your answers and the AI's damage assessment.",
               "They'll contact you about the next steps.",
               "You don't need to send anything else unless they ask."],
    "person_only": ["A claims handler has everything you told us, and any photos you sent.",
                    "They'll contact you about the next steps.",
                    "You don't need to send anything else unless they ask."],
}
# Who or what made the decision, in the customer's language. Shown right under it, so nobody has to guess whether
# a person was involved. AI lists the damage; prices and decisions come from fixed rules (never "AI decided").
HOW_DECIDED = {
    "en": {
        "paid": "<b>This claim was decided automatically.</b> No person looked at it. AI listed the damage it saw "
                "in your photos. Fixed rules then priced the repair and approved the payment.",
        "below_deductible": "<b>This was decided automatically.</b> No person looked at it. AI listed the damage "
                            "it saw in your photos, and fixed rules priced the repair from our price list. That "
                            "price is lower than your deductible, so we pay nothing on this claim.",
        "handler": "<b>How this was decided.</b> A claims handler decided this claim.",
        "review": "<b>Your claim is with a claims handler, who will make the decision.</b> AI made a first "
                  "assessment of your photos to help the claims handler. It did not decide anything.",
        "person_only": "<b>Your claim is with a claims handler, who will make the decision.</b> AI did not assess "
                       "this claim.",
        "asked": "<b>You asked for a review.</b> A claims handler now makes the decision, with your explanation "
                 "in the file. The automatic result is cancelled until then.",
    },
    "nl": {
        "paid": "<b>Over deze claim is automatisch beslist.</b> Er heeft geen medewerker naar gekeken. AI heeft op "
                "uw foto's bekeken welke schade er is. Daarna hebben vaste regels de reparatiekosten berekend en "
                "de uitkering goedgekeurd.",
        "below_deductible": "<b>Hierover is automatisch beslist.</b> Er heeft geen medewerker naar gekeken. AI heeft "
                            "op uw foto's bekeken welke schade er is, en vaste regels hebben de reparatiekosten "
                            "berekend met onze prijslijst. Dat bedrag is lager dan uw eigen risico. Daarom keren "
                            "wij op deze claim niets uit.",
        "handler": "<b>Hoe is dit beslist?</b> Een schadebehandelaar heeft over deze claim beslist.",
        "review": "<b>Uw claim ligt bij een schadebehandelaar. Die neemt de beslissing.</b> AI heeft een eerste "
                  "beoordeling van uw foto's gemaakt om de schadebehandelaar te helpen. AI heeft niets beslist.",
        "person_only": "<b>Uw claim ligt bij een schadebehandelaar. Die neemt de beslissing.</b> AI heeft deze "
                       "claim niet beoordeeld.",
        "asked": "<b>U heeft om een beoordeling gevraagd.</b> Een schadebehandelaar neemt nu de beslissing, met uw "
                 "toelichting erbij. De automatische uitkomst is tot dan vervallen.",
    },
}
ASKED_MESSAGE = {
    "en": "You asked for a review. A claims handler will review your claim and what you told us, and will "
          "contact you about the next steps.",
    "nl": "U heeft om een beoordeling gevraagd. Een schadebehandelaar beoordeelt uw claim en uw toelichting, en "
          "neemt contact met u op over de volgende stappen.",
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
    # No AI assessment ran when the chat was handed over, or when someone was hurt (core/screen.py)
    kind = "review" if (details.get("damage") or {}).get("ok") else "person_only"
    block = ("review", "With a claims handler", "A claims handler will review your claim")
    pill = ("review", "With a claims handler")
# Decided automatically, then the customer asked for a person: the rules' decision no longer stands
asked = record["status"] == "awaiting_adjuster" and decision["decision"] == "auto_settle"
how_key = "asked" if asked else "handler" if record["status"].startswith("adjuster_") else kind
how = HOW_DECIDED.get(language, HOW_DECIDED["en"])[how_key]
message = ASKED_MESSAGE.get(language, ASKED_MESSAGE["en"]) if asked else decision["customer_message"]

header(claim_id, pill, datetime.fromisoformat(record["filed_at"]).strftime("%d %B %Y, %H:%M"))

with band("paper", "status-body"), lift("status"):
    main, side = st.columns([13, 8], gap="large")
    with main, card("status"):
        theme.status_block(*block, message)
        show("<div style='height:1.2rem'></div>")
        lead = {"paid": "Assessed by", "below_deductible": "Assessed by", "review": "First check by"}.get(how_key)
        if lead:                                   # the AI mark only where AI really was involved
            theme.ai_note(how, lead=lead, link=True)
        else:
            show(f"<p class='ca-small' style='margin:0'>{how}</p>")
        if record["status"] == "settled":      # decided with no person involved: a person can be asked to review it
            with st.expander("Do you disagree, or do you want to explain something?"):
                show("<p class='ca-small' style='margin:0 0 .6rem'>You can ask a claims handler to review your "
                     "claim. If you do, the automatic result is cancelled and nothing is paid until the claims "
                     "handler has decided. The claims handler can decide on a higher or a lower amount.</p>")
                with st.form("review", border=False):
                    note = st.text_area("What should the claims handler know? (optional)", height=100,
                                        max_chars=1000)
                    if st.form_submit_button("Ask a claims handler to review"):
                        storage.request_review(claim_id, note)
                        st.rerun()

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
            ("Date", datetime.fromisoformat(claim["incident_date"]).strftime("%d %B %Y")
             if claim.get("incident_date") else "Not given"),
            ("Place", claim.get("incident_place") or "Not given"),
            ("What happened", claim.get("what_happened") or "Not given"),
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
        with_person = kind in ("review", "person_only")
        show(photo("workshop" if with_person else "canal_trees", cls="ca-side-photo", parallax=30,
                   tag="With a claims handler" if with_person else "All sorted"))

theme.footer()
