"""Branded loaders: a scan over each photo while it's checked, and a full-screen view of the claim being
processed that follows the real pipeline steps (the pipeline reports each step as it starts)."""
import base64
import html
import io
import json
import time
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

SCENE_JS = Path(__file__).parent / "loader3d.js"

STEPS = [
    ("policy", "Looking up your policy"),
    ("damage", "Assessing the damage"),
    ("details", "Checking the details"),
    ("price", "Pricing the repair"),
    ("rules", "Applying the rules"),
    ("file", "Filing your claim"),
]
# Pipeline stage -> steps that run during it. The damage and detail checks run at the same time.
STAGES = {"policy": ["policy"], "models": ["damage", "details"], "price": ["price"], "decide": ["rules"],
          "file": ["file"], "done": []}


@st.cache_data(show_spinner=False, max_entries=200)
def thumbnail(path, side=520):
    """A small JPEG as a data URI, so the browser can show a photo that only exists on the server."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((side, side))
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=72)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _scan(src):
    return f"<div class='ca-scan'><img alt='' src='{src}'><i></i><i></i><i></i><i></i></div>"


def photo_scan(path):
    return (f"<div class='ca-scanrow'>{_scan(thumbnail(path, 480))}"
            "<p><span class='ca-dots'>Checking your photo</span>"
            "<span>Is it sharp, well lit, and is the damage in view?</span></p></div>")


class ClaimRun:
    """Full-screen loader for filing a claim. Pass it to process_claim as the progress callback.
    Render it in a top-level container: a fixed overlay inside a lifted card would sit under the header."""

    def __init__(self, where, photo_paths):
        thumbs = [thumbnail(path) for path in photo_paths[:6]]
        with where:
            stage = st.empty()
            self.panel = st.empty()
        self.stage = stage
        data = html.escape(json.dumps(thumbs), quote=True)
        fallback = "".join(_scan(src) for src in thumbs[:3])
        stage.html(f"<div class='ca-overlay'><div class='stage' data-photos=\"{data}\">"
                   f"<div class='fallback'>{fallback}</div></div></div><script>{SCENE_JS.read_text()}</script>",
                   unsafe_allow_javascript=True)
        self.started, self.took, self.active = {}, {}, []
        self("policy")

    def __call__(self, stage):
        if STAGES[stage] == self.active:
            return
        now = time.time()
        for key in self.active:
            self.took[key] = now - self.started[key]
        self.active = STAGES[stage]
        for key in self.active:
            self.started[key] = now
        self._render(finished=stage == "done")

    def _render(self, finished):
        rows = []
        for number, (key, label) in enumerate(STEPS, start=1):
            if key in self.took:
                state, note = "done", f"{self.took[key]:.1f} s"
            elif key in self.active:
                state, note = "now", "running"
            else:
                state, note = "", ""
            rows.append(f"<li class='{state}'><span class='n'>{number:02d}</span>{label}<span class='s'>{note}</span></li>")
        title, sub = (("Your claim is filed", "Taking you to your claim status.") if finished else
                      ("Checking your claim", "This usually takes under a minute. Please keep this page open."))
        self.panel.html(f"<div class='ca-runpanel'><div class='ca-label'>Your claim</div><h2>{title}</h2>"
                        f"<p class='sub'>{sub}</p><ul class='ca-run'>{''.join(rows)}</ul></div>")

    def clear(self):
        self.stage.empty()
        self.panel.empty()
