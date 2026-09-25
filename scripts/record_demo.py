"""Record the home-page demo videos, one per part of the product:

    chat       a claim filed through the chat assistant, start to finish
    form       the same kind of claim through the form
    dashboard  the insurer dashboard, with the claims just filed

It drives the running app in Chrome like a person would, records the screen, and saves
static/demo_<flow>.mp4 plus a poster frame. The model calls are real, so the chat and form recordings cost
a few cents each and the outcome is whatever the rules decide.

    streamlit run app.py                                   # in another terminal
    python scripts/record_demo.py --flow form              # needs: pip install playwright
    python scripts/record_demo.py --flow chat --set small_clean --out /tmp/draft.mp4

Uses the installed Google Chrome (it plays the MP4 hero video; Playwright's own Chromium does not).
"""
import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TYPE_DELAY_MS = 32


def last_assistant_text(page):
    messages = page.locator('[class*="st-key-msg-assistant"]')
    count = messages.count()
    return (messages.nth(count - 1).inner_text() if count else "").lower(), count


def frame_chat(page):
    """Keep the chat card at the top of the screen (Streamlit scrolls the page as the chat grows)."""
    page.evaluate("""() => {
        const main = document.querySelector('section.stMain');
        const card = document.querySelector('[class*="st-key-lift-chat"]');
        if (main && card) main.scrollTo({top: main.scrollTop + card.getBoundingClientRect().top - 76});
    }""")


def wait_for_reply(page, before, timeout=90):
    """Wait until a new assistant message has arrived and the app has settled."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, count = last_assistant_text(page)
        if count > before and page.locator(".ca-skel").count() == 0:
            frame_chat(page)
            page.wait_for_timeout(900)
            return
        page.wait_for_timeout(250)
    raise TimeoutError("No reply from the assistant")


def say(page, text):
    _, before = last_assistant_text(page)
    box = page.locator('[data-testid="stChatInputTextArea"]')
    box.click()
    page.keyboard.type(text, delay=TYPE_DELAY_MS)
    page.wait_for_timeout(350)
    page.keyboard.press("Enter")
    wait_for_reply(page, before)


def press(page, name):
    _, before = last_assistant_text(page)
    page.get_by_role("button", name=name, exact=True).click()
    wait_for_reply(page, before)


def answer(page, story):
    """Reply to whatever the assistant just asked. Returns False once the confirm button is showing."""
    if page.get_by_role("button", name="Confirm and file").count():
        return False
    asked, _ = last_assistant_text(page)
    if "plate" in asked:
        press(page, "Plate")
    elif "close-up" in asked or "close up" in asked or "closeup" in asked:
        press(page, "Close-up")
    elif "wide" in asked or "whole car" in asked or "photo" in asked:
        press(page, "Wide shot")
    elif any(w in asked for w in ("police report", "repair quote", "quote", "document")):
        say(page, "No, I don't have any documents.")
    elif any(w in asked for w in ("what happened", "tell me what", "describe")):
        say(page, story["what_happened"])
    elif any(w in asked for w in ("when", "date")):
        say(page, "Yesterday afternoon.")
    elif "where" in asked:
        say(page, story["incident_place"])
    elif any(w in asked for w in ("another car", "other car", "another vehicle", "other vehicle", "other party")):
        say(page, "No, it was just me." if not story["other_party_involved"] else "Yes, another car hit me.")
    elif "driv" in asked:
        say(page, "Yes, it still drives fine." if story["drivable"] else "No, I can't drive it.")
    elif "policy" in asked:
        say(page, story["policy_number"])
    else:
        say(page, "Yes, that's right.")
    return True


def smooth_scroll(page, top, wait=1400):
    page.evaluate(f"document.querySelector('section.stMain').scrollTo({{top: {top}, behavior: 'smooth'}})")
    page.wait_for_timeout(wait)


def scroll_to(page, selector, offset=90, wait=1400):
    top = page.evaluate(f"""() => {{
        const main = document.querySelector('section.stMain');
        const el = document.querySelector({selector!r});
        return el ? main.scrollTop + el.getBoundingClientRect().top - {offset} : main.scrollTop;
    }}""")
    smooth_scroll(page, top, wait)


def record_chat(page, base_url, story):
    page.goto(f"{base_url}/chat", wait_until="networkidle")
    page.locator('[class*="st-key-msg-assistant"]').first.wait_for()
    page.wait_for_timeout(1500)
    page.locator('[class*="st-key-sidepanel"] [data-testid="stSelectbox"]').click()
    page.get_by_role("option", name=story["label"]).click()
    page.wait_for_timeout(800)
    frame_chat(page)
    for _ in range(18):
        if not answer(page, story):
            break
    page.wait_for_timeout(1500)
    page.get_by_role("button", name="Confirm and file").click()   # the 3D loader runs while the claim is checked
    page.get_by_role("button", name="View your claim status").wait_for(timeout=180_000)
    page.wait_for_timeout(4000)                                # the assistant explains the decision
    page.get_by_role("button", name="View your claim status").click()
    page.wait_for_timeout(2500)
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(3000)


def record_form(page, base_url, story):
    page.goto(f"{base_url}/claim", wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.get_by_text("Demo: fill in a ready-made claim").click()
    page.wait_for_timeout(700)
    page.locator('[data-testid="stExpander"] [data-testid="stSelectbox"]').first.click()
    page.get_by_role("option", name=story["label"]).click()
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Use this demo claim").click()
    page.wait_for_timeout(2500)
    scroll_to(page, '[class*="st-key-card-details"]', wait=1800)   # the filled-in details
    smooth_scroll(page, 900, wait=2200)
    page.get_by_role("button", name="Continue to photos").click()
    page.wait_for_timeout(1500)
    scroll_to(page, '[class*="st-key-card-photos"]', wait=500)
    page.wait_for_function("document.querySelectorAll('.ca-check').length >= 3", timeout=120_000)
    page.wait_for_timeout(1500)                                   # every photo checked
    smooth_scroll(page, 700, wait=1600)
    page.get_by_role("button", name="Continue to check").click()
    page.wait_for_timeout(2000)
    scroll_to(page, '[class*="st-key-card-review"]', wait=2000)
    smooth_scroll(page, 900, wait=1500)
    page.get_by_text("I confirm these details are correct").click()
    page.wait_for_timeout(700)
    page.get_by_role("button", name="Send my claim").click()       # the 3D loader, then the status page
    page.wait_for_url("**/status?claim=*", timeout=180_000)
    page.wait_for_timeout(3500)
    smooth_scroll(page, 450, wait=3000)
    smooth_scroll(page, 900, wait=2500)


def record_dashboard(page, base_url, story):
    page.goto(f"{base_url}/dashboard", wait_until="networkidle")
    page.wait_for_timeout(3500)                                    # headline figures
    chart = page.locator('[class*="st-key-card-chart-fraud"] canvas, [class*="st-key-card-chart-fraud"] svg').first
    box = chart.bounding_box()
    if box:                                                        # hover along the bars: tooltips
        for step in range(1, 6):
            page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * step / 7, steps=8)
            page.wait_for_timeout(500)
    page.get_by_text("All time", exact=True).click()
    page.wait_for_timeout(2500)
    scroll_to(page, '[class*="st-key-card-chart-channel"]', wait=2200)
    scroll_to(page, '[class*="st-key-card-chart-days"]', wait=2500)
    scroll_to(page, '[class*="st-key-card-channels"]', wait=2500)
    scroll_to(page, '[class*="st-key-card-recent"]', wait=3500)


FLOWS = {"chat": record_chat, "form": record_form, "dashboard": record_dashboard}


def record(base_url, flow, set_name, video_dir):
    story = json.loads((ROOT / "data" / "demo_photos" / set_name / "claim.json").read_text())
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                      record_video_dir=str(video_dir), record_video_size={"width": 1440, "height": 900})
        page = context.new_page()
        FLOWS[flow](page, base_url, story)
        video = page.video.path()
        context.close()
        browser.close()
    return Path(video)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flow", choices=list(FLOWS), default="chat")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--set", default="small_clean")
    parser.add_argument("--out", help="default: static/demo_<flow>.mp4")
    args = parser.parse_args()
    out = Path(args.out or ROOT / "static" / f"demo_{args.flow}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "/opt/anaconda3/bin/ffmpeg"
    with tempfile.TemporaryDirectory() as tmp:
        raw = record(args.url, args.flow, args.set, Path(tmp))
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-vf", "scale=1280:-2", "-c:v", "libx264",
                        "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
                        str(out)], check=True)
    poster = out.with_name(out.stem + "_poster.jpg")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "3", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                    str(poster)], check=True)
    print(f"Saved {out} ({out.stat().st_size / 1e6:.1f} MB) and {poster.name}")


if __name__ == "__main__":
    main()
