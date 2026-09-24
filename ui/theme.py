"""Look and feel: colour tokens, type, and a few page components.
Palette: calm indigo base (trust, low arousal) with fresh green as the one bright accent."""
import html

import streamlit as st

from core import config

APP_NAME = "Claims Agent"          # working name, change here

INK, PRIMARY, TINT, CANVAS, LINE = "#1B2340", "#2F4A8A", "#E8ECF8", "#F6F7FA", "#DDE1EA"
GREEN, GREEN_TEXT, MUTED, ERROR = "#3CCB7F", "#1E7A4C", "#4A5268", "#B42318"

# Unsplash photos, loaded straight from Unsplash with a credit line.
PHOTOS = {
    "start": ("https://images.unsplash.com/photo-1564145329150-1f926a0a4924", "milan degraeve", "milandegraeve"),
    "form": ("https://images.unsplash.com/photo-1640129700000-6326d7b811d8", "Jonas Schöne", "schoene"),
    "status": ("https://images.unsplash.com/photo-1669586618689-830661fe3b39", "Kateryna Melnyk", "katranos"),
}

CSS = f"""
<style>
:root {{
  --ink: {INK}; --primary: {PRIMARY}; --tint: {TINT}; --canvas: {CANVAS}; --line: {LINE};
  --green: {GREEN}; --green-text: {GREEN_TEXT}; --muted: {MUTED}; --error: {ERROR};
  --display: "Schibsted Grotesk", "Helvetica Neue", Arial, sans-serif;
}}
[data-testid="stDecoration"], [data-testid="stStatusWidget"], footer {{ display: none !important; }}
[data-testid="stHeader"] {{ background: #FFFFFF; border-bottom: 1px solid var(--line); }}
[data-testid="stMainBlockContainer"] {{ max-width: 1180px; padding: 6.5rem 2rem 4rem; }}
h1, h2, h3 {{ font-family: var(--display) !important; color: var(--ink) !important; letter-spacing: -0.02em; }}
h1 {{ font-size: 2.9rem !important; line-height: 1.08 !important; font-weight: 600 !important; }}
h2 {{ font-size: 1.6rem !important; font-weight: 600 !important; }}
h3 {{ font-size: 1.15rem !important; font-weight: 600 !important; }}
p, li, label {{ color: var(--ink); }}

/* Buttons: green primary with ink text (white on green fails contrast), quiet secondary */
[data-testid="stBaseButton-primary"] {{ background: var(--green) !important; border-color: var(--green) !important;
  color: var(--ink) !important; font-weight: 600; padding: 0.6rem 1.2rem; }}
[data-testid="stBaseButton-primary"]:hover {{ background: #33B872 !important; border-color: #33B872 !important; }}
[data-testid="stBaseButton-primary"] p {{ color: var(--ink) !important; }}
[data-testid="stBaseButton-secondary"] {{ background: #FFFFFF; color: var(--ink); border-color: var(--line); }}
[data-testid="stBaseButton-secondary"]:hover {{ border-color: var(--primary); color: var(--primary); }}

/* Inputs */
[data-testid="stFileUploaderDropzone"] {{ background: #FFFFFF; border: 1px dashed #B8BFD0; border-radius: 4px; }}
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{ background: #FFFFFF; }}

/* Components */
.ca-eyebrow {{ display: flex; align-items: center; gap: 10px; font-size: 0.8rem; font-weight: 600;
  letter-spacing: 0.04em; color: var(--primary); margin-bottom: 1rem; }}
.ca-eyebrow::before {{ content: ""; width: 28px; height: 3px; background: var(--green); }}
.ca-lede {{ font-size: 1.12rem; line-height: 1.65; color: var(--muted); max-width: 34rem; margin: 0.4rem 0 0; }}
.ca-photo {{ width: 100%; display: block; object-fit: cover !important; border-radius: 2px; }}
.ca-credit {{ font-size: 0.72rem; color: #8A91A6; margin-top: 0.5rem; }}
.ca-credit a {{ color: #8A91A6; text-decoration: underline; }}
.ca-rule {{ border-top: 1px solid var(--line); margin: 2.5rem 0 1.5rem; }}
.ca-option {{ border-top: 1px solid var(--line); padding: 1.3rem 0 0.2rem; }}
.ca-option h3 {{ margin: 0 0 0.25rem; padding: 0; }}
.ca-option p {{ color: var(--muted); margin: 0 0 0.8rem; font-size: 0.95rem; }}
.ca-small {{ font-size: 0.85rem; color: var(--muted); }}
.ca-steps {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 0.5rem 0 2.2rem; }}
.ca-step {{ font-size: 0.85rem; color: #8A91A6; padding-top: 10px; border-top: 3px solid var(--line); }}
.ca-step.done {{ border-top-color: var(--green); color: var(--muted); }}
.ca-step.now {{ border-top-color: var(--green); color: var(--ink); font-weight: 600; }}
.ca-status {{ background: #FFFFFF; border: 1px solid var(--line); border-radius: 4px; padding: 1.6rem 1.8rem; }}
.ca-status .label {{ font-size: 0.8rem; font-weight: 600; margin: 0 0 0.4rem; }}
.ca-status .title {{ font-family: var(--display); font-size: 1.9rem; font-weight: 600; letter-spacing: -0.02em;
  line-height: 1.15; margin: 0 0 0.6rem; color: var(--ink); }}
.ca-status .body {{ color: var(--muted); line-height: 1.65; margin: 0; }}
.ca-status.settled {{ border-top: 4px solid var(--green); }}
.ca-status.settled .label {{ color: var(--green-text); }}
.ca-status.review {{ border-top: 4px solid var(--primary); }}
.ca-status.review .label {{ color: var(--primary); }}
.ca-check {{ font-size: 0.88rem; margin: 0.4rem 0 0; }}
.ca-check.ok {{ color: var(--green-text); }}
.ca-check.retake {{ color: var(--ink); background: var(--tint); padding: 0.6rem 0.8rem; border-radius: 2px; }}
.ca-kv {{ display: grid; grid-template-columns: 11rem 1fr; gap: 0.55rem 1rem; font-size: 0.95rem; }}
.ca-kv dt {{ color: var(--muted); }}
.ca-kv dd {{ margin: 0; color: var(--ink); }}
.ca-foot {{ font-size: 0.75rem; color: #8A91A6; margin-top: 3.5rem; padding-top: 1rem; border-top: 1px solid var(--line); }}
@media (max-width: 720px) {{
  [data-testid="stMainBlockContainer"] {{ padding: 8.5rem 1rem 3rem; }}
  h1 {{ font-size: 2.1rem !important; }}
  .ca-kv {{ grid-template-columns: 1fr; }}
}}
</style>
"""

LOGO = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='220' height='40'>"
    "<rect x='0' y='12' width='16' height='16' fill='%233CCB7F'/>"
    "<rect x='6' y='6' width='16' height='16' fill='none' stroke='%231B2340' stroke-width='2.5'/>"
    "<text x='34' y='27' font-family='Helvetica Neue, Arial, sans-serif' font-size='19' font-weight='700' "
    f"fill='%231B2340' letter-spacing='-0.5'>{APP_NAME}</text></svg>"
)


def apply():
    st.html(CSS)
    st.logo(LOGO, size="medium")


def password_gate():
    """Protects the deployed link. Local runs (localhost) skip it."""
    password = config.secret("APP_PASSWORD")
    host = st.context.headers.get("Host", "")
    if not password or host.startswith(("localhost", "127.0.0.1")) or st.session_state.get("authed"):
        return True
    st.markdown(f"<div class='ca-eyebrow'>{APP_NAME}</div>", unsafe_allow_html=True)
    st.markdown("## Team access")
    entered = st.text_input("Password", type="password")
    if st.button("Continue", type="primary"):
        if entered == password:
            st.session_state["authed"] = True
            st.rerun()
        st.error("That password isn't right.")
    return False


def eyebrow(text):
    st.markdown(f"<div class='ca-eyebrow'>{html.escape(text)}</div>", unsafe_allow_html=True)


def lede(text):
    st.markdown(f"<p class='ca-lede'>{html.escape(text)}</p>", unsafe_allow_html=True)


def photo(key, height=560, crop="entropy"):
    base, name, username = PHOTOS[key]
    utm = "?utm_source=claims_agent_prototype&utm_medium=referral"
    st.markdown(
        f"<img class='ca-photo' style='height:{height}px' alt='' "
        f"src='{base}?w=1400&q=80&fm=jpg&fit=crop&crop={crop}'>"
        f"<div class='ca-credit'>Photo by <a href='https://unsplash.com/@{username}{utm}' target='_blank'>{name}</a>"
        f" on <a href='https://unsplash.com/{utm}' target='_blank'>Unsplash</a></div>",
        unsafe_allow_html=True,
    )


def steps(labels, current):
    cells = []
    for index, label in enumerate(labels):
        state = "done" if index < current else "now" if index == current else ""
        cells.append(f"<div class='ca-step {state}'>{html.escape(label)}</div>")
    st.markdown(f"<div class='ca-steps'>{''.join(cells)}</div>", unsafe_allow_html=True)


def status_block(kind, label, title, body):
    st.markdown(
        f"<div class='ca-status {kind}'><p class='label'>{html.escape(label)}</p>"
        f"<p class='title'>{html.escape(title)}</p><p class='body'>{html.escape(body)}</p></div>",
        unsafe_allow_html=True,
    )


def key_values(rows):
    items = "".join(f"<dt>{html.escape(k)}</dt><dd>{html.escape(str(v))}</dd>" for k, v in rows)
    st.markdown(f"<dl class='ca-kv'>{items}</dl>", unsafe_allow_html=True)


def footer():
    st.markdown(
        "<div class='ca-foot'>Prototype for the RSM AI Strategy Lab. Demo policies and test data only; "
        "no real claims are processed.</div>",
        unsafe_allow_html=True,
    )
