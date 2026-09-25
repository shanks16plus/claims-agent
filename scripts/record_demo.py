"""Record the home-page demo video: a real claim filed through the chat, start to finish.

It drives the running app in Chrome like a customer would (types answers, sends the demo photos, confirms),
records the screen, and saves static/demo.mp4 plus a poster frame. The model calls are real, so each
recording costs a few cents and the outcome is whatever the rules decide.

    streamlit run app.py                                   # in another terminal
    python scripts/record_demo.py                          # needs: pip install playwright
    python scripts/record_demo.py --set small_clean --out /tmp/draft.mp4

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


def record(base_url, set_name, video_dir):
    story = json.loads((ROOT / "data" / "demo_photos" / set_name / "claim.json").read_text())
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                      record_video_dir=str(video_dir), record_video_size={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(base_url, wait_until="networkidle")
        page.wait_for_timeout(3500)                               # the hero: headline, video
        page.get_by_role("button", name="Chat with the assistant").first.click()
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
        video = page.video.path()
        context.close()
        browser.close()
    return Path(video)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--set", default="small_clean")
    parser.add_argument("--out", default=str(ROOT / "static" / "demo.mp4"))
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "/opt/anaconda3/bin/ffmpeg"
    with tempfile.TemporaryDirectory() as tmp:
        raw = record(args.url, args.set, Path(tmp))
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-vf", "scale=1280:-2", "-c:v", "libx264",
                        "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
                        str(out)], check=True)
    poster = out.with_name(out.stem + "_poster.jpg")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "2", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                    str(poster)], check=True)
    print(f"Saved {out} ({out.stat().st_size / 1e6:.1f} MB) and {poster.name}")


if __name__ == "__main__":
    main()
