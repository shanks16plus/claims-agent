"""Start screen: what the service does, a screen recording of a real run, how a claim is decided,
and the two ways in (form or chat)."""
import streamlit as st

from core import config
from ui import theme
from ui.theme import band, heading, photo, show


def entry_buttons(key):
    with st.container(horizontal=True, gap="small", key=f"{key}-actions"):
        if st.button("Start the form", key=f"{key}_form", type="primary"):
            st.switch_page("views/claim_form.py")
        if st.button("Chat with the assistant", key=f"{key}_chat"):
            st.switch_page("views/chat.py")


# --- Hero: looping video under deep navy --------------------------------------------------------
with band("hero-home", "home"):
    theme.hero_media("start", video=theme.HERO_VIDEO)
    heading("Car damage claims", "Report car damage in a few minutes",
            "Tell us what happened and add a few photos. We check your claim straight away, and if anything "
            "needs a closer look, a claims handler takes it from there.", size="display", split=True)
    entry_buttons("hero")
    show("<p class='ca-note-line' data-reveal='fade' data-delay='1'>You'll need your policy number and a phone "
         "camera. Most people finish in about five minutes.</p>")

# --- How it works: numbered steps beside a photo that follows the step in view -----------------------
STEPS = [
    ("phone", "Tell us what happened",
     "Your policy number, the date and place, which side of the car was hit, and whether another car was "
     "involved. The form asks it all on one page; in the chat, the assistant asks one question at a time."),
    ("start", "Add three kinds of photo",
     "A wide shot of the car, a close-up of each damaged area and the number plate. Each photo is checked as "
     "you add it, so you know straight away if one needs a retake."),
    ("workshop", "Get a decision",
     "Small, clear claims are settled on the spot, with the amount shown. Everything else goes to a claims "
     "handler, with your photos and answers already in one file."),
]
with band("paper", "how"):
    heading("How it works", "What happens when you report damage", index="01")
    media = "".join(photo(key, cls="on" if i == 0 else "", reveal=None, width=1100, attrs=f"data-i='{i}'")
                    for i, (key, _, _) in enumerate(STEPS))
    steps = "".join(
        f"<div class='ca-how-step{' on' if i == 0 else ''}' data-i='{i}'>"
        f"{photo(key, cls='inline', reveal=None, width=900)}<span class='n'>{i + 1}</span>"
        f"<div><h3>{title}</h3><p>{body}</p></div></div>"
        for i, (key, title, body) in enumerate(STEPS))
    show(f"<div class='ca-how' data-how><div class='ca-how-media' data-reveal='clip'>{media}</div>"
         f"<div class='ca-how-steps' data-reveal='up' data-delay='0.15'>{steps}</div></div>")

# --- Everyday damage: a slow strip of street photos -----------------------------------------------------
with band("ink", "streets"):
    heading("Everyday damage", "Built for the claims people make most often: scrapes, dents and broken lights",
            "Small damage is common and easy to show with a phone. That makes it a good fit for a quick "
            "check, with a person stepping in whenever the damage is bigger or unclear.", index="02")
    strip = "".join(photo(key, reveal=None, width=900)
                    for key in ["canal", "cafe", "street", "status", "canal_trees", "form"] * 2)
    show(f"<div class='ca-strip' data-reveal='fade' data-delay='0.3'><div class='track'>{strip}</div></div>")

# --- See it in action: unedited screen recordings, one per part of the product ---------------------------------
DEMOS = {
    "Chat": ("demo_chat", "A claim filed through the chat assistant and settled on the spot: estimate €1,326.76, "
                          "payout €1,076.76 after the deductible."),
    "Form": ("demo_form", "The same kind of claim through the form, also settled on the spot: estimate €1,021.24, "
                          "payout €771.24."),
    "Insurer dashboard": ("demo_dashboard", "What the insurer sees: every claim, what the rules decided, fraud "
                                            "flags and the model cost per claim."),
}
available = {label: demo for label, demo in DEMOS.items() if (config.ROOT / "static" / f"{demo[0]}.mp4").exists()}
if available:
    with band("stone", "demo"):
        heading("See it in action", "The prototype at work, start to finish",
                "Unedited screen recordings with real model calls: a claim through the chat, the same kind of claim "
                "through the form, and what the insurer sees. Nothing is sped up.", index="03")
        pick = st.segmented_control("Recording", list(available), default=next(iter(available)), required=True,
                                    label_visibility="collapsed", key="demo_pick")
        name, caption = available[pick]
        show(f"<div class='ca-demo' data-reveal='fade'><div class='ca-video demo' data-src='app/static/{name}.mp4' "
             f"data-controls='1'><img alt='' src='app/static/{name}_poster.jpg'></div></div>"
             f"<p class='ca-small' style='margin-top:.8rem'>{caption} Recorded on 25 September 2026 with the "
             "fictional demo policy NL-100001. The car photo is by AVDLCZ on Wikimedia Commons (CC0).</p>")

# --- How a claim is decided: the governance split, drawn as a live diagram -----------------------------------
FLOW_SVG = """<svg viewBox='0 0 1100 300' role='img' aria-label='Your photos and story go to the AI, which assesses the damage.
Fixed rules in code then either settle the claim on the spot or pass it to a claims handler.'>
  <path id='w1' class='wire' data-order='1' d='M220,150 H290'/>
  <path id='w2' class='wire' data-order='2' d='M510,150 H580'/>
  <path id='w3' class='wire go' data-order='3' d='M800,150 C842,150 838,60 880,60'/>
  <path id='w4' class='wire' data-order='3' d='M800,150 C842,150 838,240 880,240'/>
  <g transform='translate(0,104)'><g class='node' data-order='0'><rect width='220' height='92'/>
    <text class='k' x='18' y='28'>You</text><text class='t' x='18' y='55'>Photos and story</text>
    <text class='s' x='18' y='77'>From the form or the chat</text></g></g>
  <g transform='translate(290,104)'><g class='node ai' data-order='1'><rect width='220' height='92'/>
    <text class='k' x='18' y='28'>AI model</text><text class='t' x='18' y='55'>Assesses the damage</text>
    <text class='s' x='18' y='77'>Parts, severity, confidence</text></g></g>
  <g transform='translate(580,104)'><g class='node rules' data-order='2'><rect width='220' height='92'/>
    <text class='k' x='18' y='28'>Plain code</text><text class='t' x='18' y='55'>Fixed rules decide</text>
    <text class='s' x='18' y='77'>Prices, limits and checks</text></g></g>
  <g transform='translate(880,14)'><g class='node settle' data-order='3'><rect width='220' height='92'/>
    <text class='k' x='18' y='28'>Clear and small</text><text class='t' x='18' y='55'>Settled on the spot</text>
    <text class='s' x='18' y='77'>Payout worked out in code</text></g></g>
  <g transform='translate(880,194)'><g class='node human' data-order='3'><rect width='220' height='92'/>
    <text class='k' x='18' y='28'>Anything else</text><text class='t' x='18' y='55'>A claims handler</text>
    <text class='s' x='18' y='77'>With the file already prepared</text></g></g>
  <circle class='pulse' r='4' data-route='w1,w2,w3'/>
  <circle class='pulse human' r='4' data-route='w1,w2,w4'/>
</svg>"""
FLOW_LIST = """<ol class='ca-flow-list'>
  <li><div><b>Photos and story</b>From the form or the chat</div></li>
  <li><div><b>The AI model assesses the damage</b>Parts, severity, confidence</div></li>
  <li><div><b>Fixed rules in code decide</b>Prices, limits and checks</div></li>
  <li><div><b>Settled on the spot, or a claims handler</b>Only clear, small claims are settled automatically</div></li>
</ol>"""

with band("night", "decide"):
    heading("How a claim is decided", "The model looks at the damage. Fixed rules decide what happens next.",
            "An AI model reads your description and looks at your photos. Whether a claim is paid is decided by "
            "rules in plain code, which are the same for every customer. The model cannot set a price, and it "
            "cannot reject a claim.", index="04")
    show(f"<div class='ca-flow' data-reveal='fade' data-flow>{theme.svg(FLOW_SVG)}{FLOW_LIST}</div>")
    confidence = round(config.MIN_CONFIDENCE_AUTO * 100)
    show("<div class='ca-ledger' data-reveal='stagger' data-delay='0.2'>"
         "<div class='row'><div class='rule'><b>Settled on the spot only below this estimate</b>Above it, a claims "
         "handler decides.</div><div class='value'>€<span data-count='{0}'>{1}</span></div></div>"
         "<div class='row'><div class='rule'><b>How sure the damage check must be</b>Below this, a person looks at "
         "the photos.</div><div class='value'><span data-count='{2}'>{2}</span>%</div></div>"
         "<div class='row'><div class='rule'><b>Claims the AI can reject</b>If the rules don't allow an automatic "
         "payout, a person decides.</div><div class='value'>None</div></div></div>"
         .format(config.AUTO_SETTLE_MAX_EUR, f"{config.AUTO_SETTLE_MAX_EUR:,}", confidence))

# --- When a person takes over ---------------------------------------------------------------------------------
with band("paper", "handover"):
    left, right = st.columns([11, 10], gap="large", vertical_alignment="center")
    with left:
        show(photo("bumper", cls="ca-split-photo", parallax=40, tag="From claim to repair"))
    with right:
        heading("When a person takes over", "A claims handler gets the whole file",
                "They see everything in one place, so you don't have to explain it all again.", index="05")
        show("<ul class='ca-deflist' data-reveal='stagger' data-delay='0.3'>"
             "<li>Your photos and answers</li>"
             "<li>The damage assessment and a cost breakdown per part</li>"
             "<li>The rules the claim did not pass, and a suggested next step</li></ul>")

# --- Closing call to action -------------------------------------------------------------------------------------
with band("hero-cta", "cta"):
    theme.hero_media("rotterdam", even=True)
    heading("Start a claim", "Report damage while the details are still fresh.", size="title", split=True)
    entry_buttons("cta")

theme.footer()
