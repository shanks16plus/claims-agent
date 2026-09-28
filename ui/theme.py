"""Look and feel: colour tokens, photos, full-width bands and a few page components.
Palette: deep navy carries the brand, green is the one accent, warm paper neutrals instead of white.
Styles are in theme.css, page motion (GSAP) in motion.js."""
import base64
import html
from pathlib import Path

import streamlit as st

from core import config

APP_NAME = "Claims Agent"          # working name, change here
HERE = Path(__file__).parent

# Unsplash photos, loaded straight from Unsplash: (image id, photographer, Unsplash username)
PHOTOS = {
    "start": ("photo-1564145329150-1f926a0a4924", "milan degraeve", "milandegraeve"),
    "form": ("photo-1640129700000-6326d7b811d8", "Jonas Schöne", "schoene"),
    "status": ("photo-1669586618689-830661fe3b39", "Kateryna Melnyk", "katranos"),
    "phone": ("photo-1676904630439-08cb153a0a81", "Panagiotis Falcos", "falcos"),
    "workshop": ("photo-1767681092416-bccf9410bda4", "Winston Chen", "winstonchen"),
    "bumper": ("photo-1786489785778-a163f38b7c87", "Zoshua Colah", "zoshuacolah"),
    "canal": ("photo-1782037492903-35749597f3ff", "Hilderose", "hilderose"),
    "canal_trees": ("photo-1766247096324-ff0e9a77c927", "Nikolai Kolosov", "nikolaikolosov"),
    "cafe": ("photo-1789652121318-7ad481c346fc", "Fons Heijnsbroek", "fonsheijnsbroek_amsterdam_photos"),
    "street": ("photo-1766247096270-ae0ebbb27da1", "Nikolai Kolosov", "nikolaikolosov"),
    "rotterdam": ("photo-1725100612113-a62c4b1304f0", "Julia Taubitz", "justmejuliee"),
}
# Looping hero video: aerial view of a car after a collision (Mixkit free licence, no attribution needed).
HERO_VIDEO = "https://assets.mixkit.co/videos/49234/49234-720.mp4"
UTM = "?utm_source=claims_agent_prototype&utm_medium=referral"


def apply():
    st.html(HERE / "theme.css")
    st.html(f"<script>{(HERE / 'motion.js').read_text()}</script>", unsafe_allow_javascript=True)
    st.logo(_logo(), size="medium")


def _logo():
    return ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='40'>"
            "<rect x='0' y='14' width='12' height='12' fill='%232FAE6B'/>"
            "<text x='22' y='27' font-family='Georgia, Times New Roman, serif' font-size='20' "
            f"fill='%230F1D2E'>{APP_NAME}</text></svg>")


def esc(text):
    return html.escape(str(text))


# --- Layout ---------------------------------------------------------------------------
def demo_mode():
    """Hidden developer switch for the screen recordings (scripts/record_demo.py): ?demo=1 in the URL shows the
    ready-made demo claims. Everyone else types the details and uploads photos, like a customer (see test_kit/)."""
    return st.query_params.get("demo") == "1"


def band(tone, name):
    """A full-width section. Tones: paper, surface, stone, ink, night, hero-home, hero-page, hero-cta.
    Start the name with "tight" for less padding."""
    return st.container(key=f"band-{tone}-{name}")


def card(name):
    """A white panel inside a band."""
    return st.container(key=f"card-{name}")


def lift(name):
    """Content pulled up over the hero band above it."""
    return st.container(key=f"lift-{name}")


def show(markup):
    st.html(markup)


def svg(markup, cls=""):
    """st.html strips SVG, so it travels base64-encoded and motion.js unpacks it in the page."""
    data = base64.b64encode(markup.encode()).decode("ascii")
    return f"<div class='ca-svg {cls}' data-svg='{data}'></div>"


# --- Photos ---------------------------------------------------------------------------
def photo_url(key, width=1600):
    return f"https://images.unsplash.com/{PHOTOS[key][0]}?w={width}&q=80&fm=jpg&fit=crop&auto=format"


def photo(key, height=None, cls="", reveal="clip", parallax=None, tag=None, width=1400, delay=0, attrs=""):
    """HTML for a photo block. The credit goes in the footer."""
    style = f" style='height:{height}px'" if height else ""
    extra = f" {attrs}" if attrs else ""
    extra += f" data-parallax='{parallax}'" if parallax else ""
    extra += f" data-reveal='{reveal}' data-delay='{delay}'" if reveal else ""
    label = f"<span class='tag'>{esc(tag)}</span>" if tag else ""
    return (f"<div class='ca-photo {cls}'{style}{extra}>"
            f"<img alt='' loading='lazy' src='{photo_url(key, width)}'>{label}</div>")


def hero_media(photo_key=None, video=None, even=False):
    """The first element in a hero band: a photo, and optionally a looping muted video over it,
    under an indigo shade. motion.js creates the video element; the photo stays as the fallback."""
    still = f"<img class='zoom' alt='' src='{photo_url(photo_key, 1800)}'>" if photo_key else ""
    moving = f"<div class='ca-video' data-src='{video}'></div>" if video else ""
    shade = " even" if even else ""
    st.html(f"<div class='ca-media{shade}'>{still}{moving}</div>")


# --- Text -----------------------------------------------------------------------------
def label(text, index=None, delay=0):
    number = f"<b>{index}</b>" if index else ""
    return f"<div class='ca-label' data-reveal='fade' data-delay='{delay}'>{number}{esc(text)}</div>"


def heading(eyebrow=None, title=None, lede=None, size="title", split=False, delay=0, index=None):
    parts = [label(eyebrow, index, delay)] if eyebrow else []
    if title:
        tag = "h1" if size in ("display", "page-title") else "h2"
        motion = "data-split" if split else ""
        parts.append(f"<{tag} class='ca-{size}' data-reveal='up' {motion} data-delay='{delay + 0.1}'>{title}</{tag}>")
    if lede:
        parts.append(f"<p class='ca-lede' data-reveal='up' data-delay='{delay + 0.35}'>{esc(lede)}</p>")
    st.html("".join(parts))


def progress(labels, current):
    cells = []
    for index, label in enumerate(labels):
        state = "done" if index < current else "now" if index == current else ""
        cells.append(f"<div class='{state}'><b>0{index + 1}</b>{esc(label)}</div>")
    st.html(f"<div class='ca-progress'>{''.join(cells)}</div>")


def status_block(kind, label, title, body):
    st.html(f"<div class='ca-status {kind}' data-reveal='up'><p class='label'>{esc(label)}</p>"
            f"<p class='title'>{esc(title)}</p><p class='body'>{esc(body)}</p></div>")


def key_values(rows, total=False):
    items = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows)
    st.html(f"<dl class='ca-kv{' total' if total else ''}'>{items}</dl>")


def small_heading(text):
    st.html(f"<p class='ca-h'>{esc(text)}</p>")


# --- Footer and access ------------------------------------------------------------------
def footer(slim=False):
    """The site footer. slim=True: one line for the internal (insurer) pages."""
    if slim:
        with band("paper", "tight-footer-slim"):
            with st.container(horizontal=True, gap="medium", vertical_alignment="center"):
                st.html(f"<p class='ca-footline'>{APP_NAME} prototype, RSM AI Strategy Lab. Fictional policies "
                        "and test data.</p>")
                st.page_link("views/legal.py", label="Privacy and terms")
        return
    seen, credits = set(), []
    for _, name, username in PHOTOS.values():
        if username not in seen:
            seen.add(username)
            credits.append(f"<a href='https://unsplash.com/@{username}{UTM}' target='_blank'>{esc(name)}</a>")
    with band("night", "tight-footer"):
        st.html(
            "<div class='ca-footer'><div>"
            f"<div class='brand'><i></i>{APP_NAME}</div>"
            "<p>A prototype built for the RSM AI Strategy Lab. It uses fictional policies and test photos, and "
            "no real claims are paid. An AI model reads each claim; prices, limits and the final decision are set "
            "in code, and anything unclear goes to a person.</p></div>"
            f"<div><p>Photos on <a href='https://unsplash.com/{UTM}' target='_blank'>Unsplash</a> by "
            f"{', '.join(credits)}. Hero video from <a href='https://mixkit.co/' target='_blank'>Mixkit</a>.</p>"
            "</div></div>")
        st.page_link("views/legal.py", label="Privacy notice and terms of use")


def password_gate():
    """Protects the deployed link. Local runs (localhost) skip it."""
    password = config.secret("APP_PASSWORD")
    host = st.context.headers.get("Host", "")
    if not password or host.startswith(("localhost", "127.0.0.1")) or st.session_state.get("authed"):
        return True
    with band("hero-page", "gate"):
        hero_media("rotterdam", even=True)
        heading(APP_NAME, "Team access", size="page-title")
    with band("canvas", "gate-form"):
        with lift("gate"), card("gate"):
            entered = st.text_input("Password", type="password")
            if st.button("Continue", type="primary"):
                if entered == password:
                    st.session_state["authed"] = True
                    st.rerun()
                st.error("That password isn't right.")
    return False
