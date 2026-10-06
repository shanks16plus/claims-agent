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

Stills for slides. With --stills FOLDER the chat run also saves PNG stills of single parts of the screens (at
device scale factor 2) and run.json, the numbers of that claim read from the claims log:

    python scripts/record_demo.py --flow chat --stills data/runtime/deck_assets            # video and stills
    python scripts/record_demo.py --flow chat --set large --stills FOLDER --no-video --parts status,file
    python scripts/record_demo.py --flow stills --claim CLM-... --stills FOLDER            # a claim already filed

Parts: chat (needs the live chat run), status, file (the Claim file on the dashboard), dashboard, home.

Uses the installed Google Chrome (it plays the MP4 hero video; Playwright's own Chromium does not).
"""
import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "data" / "runtime"
TYPE_DELAY_MS = 32
VIEWPORT = {"width": 1440, "height": 900}                 # what a recording shows
# Headless Chrome keeps about 87 points at the bottom of its window for itself, which the recorder sees as a grey
# strip. So the page is laid out a little taller and only the top VIEWPORT part of the recording is kept.
PAGE = {"width": VIEWPORT["width"], "height": VIEWPORT["height"] + 90}
PARTS = ["chat", "status", "file", "dashboard", "home"]


# --- Stills -----------------------------------------------------------------------------------------------------
# Small JavaScript helpers for finding one part of a page: a heading by its text, and everything from one
# heading up to the next (a Range has a bounding box, like an element).
FINDERS = """
const one = (selector, root) => (root || document).querySelector(selector);
const all = (selector, root) => [...(root || document).querySelectorAll(selector)];
const heading = (root, text) => all('.ca-h', root).find(h => h.innerText.trim().startsWith(text));
const label = (root, text) => all('.ca-label', root).find(l => l.innerText.toLowerCase().includes(text));
const section = (root, from, to) => {
    const start = heading(root, from), end = to && heading(root, to);
    if (!start) return null;
    const range = document.createRange();
    range.setStartBefore(start);
    end ? range.setEndBefore(end) : range.setEndAfter(root.lastElementChild);
    return range;
};
"""


class Stills:
    """Numbered PNG stills of single parts of a page. The pages are opened at device scale factor 2."""

    def __init__(self, folder, parts):
        self.folder, self.parts, self.saved, self.missed = Path(folder), parts, [], []
        self.folder.mkdir(parents=True, exist_ok=True)

    def wants(self, part):
        return part in self.parts

    def box(self, page, find):
        """The box around what `find` returns (JavaScript: elements or ranges), in window coordinates."""
        return page.evaluate(f"""() => {{
            {FINDERS}
            const boxes = [{find}].flat().filter(Boolean).map(e => e.getBoundingClientRect()).filter(b => b.width && b.height);
            if (!boxes.length) return null;
            const left = Math.min(...boxes.map(b => b.left)), top = Math.min(...boxes.map(b => b.top));
            return {{x: left, y: top, width: Math.max(...boxes.map(b => b.right)) - left,
                    height: Math.max(...boxes.map(b => b.bottom)) - top}};
        }}""")

    def save(self, page, name, find, pad=12, fit=True):
        """Save the part of the page that `find` covers, with a small margin. fit=True scrolls the part to the top
        and makes the window taller when needed; fit=False takes only what is on screen now, so a recording that is
        running is left alone."""
        box = self.box(page, find)
        if box is None:
            self.missed.append(name)
            print(f"  still not saved, the part is not on this page: {name}")
            return
        size = page.viewport_size
        if fit:
            if box["height"] + 2 * pad + 100 > size["height"]:
                page.set_viewport_size({"width": size["width"], "height": int(box["height"] + 2 * pad + 160)})
                page.wait_for_timeout(700)
            page.evaluate(f"""() => {{ {FINDERS}
                const main = one('section.stMain'), target = [{find}].flat().filter(Boolean)[0];
                main.scrollTo({{top: main.scrollTop + target.getBoundingClientRect().top - {pad + 70}}}); }}""")
            page.wait_for_timeout(900)
            box, size = self.box(page, find), page.viewport_size
        left, top = max(0, box["x"] - pad), max(0, box["y"] - pad)
        clip = {"x": left, "y": top, "width": min(size["width"], box["x"] + box["width"] + pad) - left,
                "height": min(size["height"], box["y"] + box["height"] + pad) - top}
        path = self.folder / f"{name}.png"
        page.screenshot(path=str(path), clip=clip)
        self.saved.append(path.name)
        print(f"  still {path.name}  {round(clip['width'])} x {round(clip['height'])} points")


CHECKLIST = "label(one('[class*=\"st-key-sidepanel\"]'), 'claim checklist'), one('.ca-checklist'), one('.ca-meter')"
CONFIRM_CARD = "one('[class*=\"st-key-card-confirm\"]')"
TOOL_LOG = "label(one('[class*=\"st-key-sidepanel\"]'), 'tool calls'), all('.ca-log')"
NEWEST_LOG_ROWS = "label(one('[class*=\"st-key-sidepanel\"]'), 'tool calls'), all('.ca-log').slice(0, 7)"
LAST_MESSAGES = "all('[class*=\"st-key-msg-assistant\"]').slice(-2)"
# From the first photo the customer sent to the assistant's reply after the last one
PHOTO_TURNS = """(() => { const turns = all('[class*="st-key-msg-"]'), sent = turns.filter(t => t.querySelector('img'));
    return sent.length ? turns.slice(turns.indexOf(sent[0]), turns.indexOf(sent[sent.length - 1]) + 2) : []; })()"""


# The conversation sits in a box of fixed height that scrolls. For a still of several turns the box and the
# wrapper that gives it its height are both let go, so the page simply grows.
OPEN_CHAT_LOG = """() => { const log = document.querySelector('[class*="st-key-chatlog"]');
    for (const el of [log, log.parentElement]) {
        el.style.flex = '0 0 auto'; el.style.height = 'auto'; el.style.maxHeight = 'none'; el.style.overflow = 'visible';
    } }"""


def photos_accepted(page):
    return page.evaluate("document.querySelectorAll('.ca-checklist li.filled').length"
                         " && [...document.querySelectorAll('.ca-checklist li em')].filter(e => /accepted/.test(e.innerText)).length")


def chat_stills_afterwards(page, stills):
    """After the part of the recording we keep: back to the chat (same session), with the conversation opened to
    its full length and a tall window, for the stills that need more than one screen."""
    page.go_back()
    page.locator('[class*="st-key-chatlog"]').wait_for(timeout=30_000)
    page.set_viewport_size({"width": PAGE["width"], "height": 2400})
    page.wait_for_timeout(1500)
    page.evaluate(OPEN_CHAT_LOG)
    page.wait_for_timeout(1200)
    stills.save(page, "01_chat_photos", PHOTO_TURNS)
    stills.save(page, "04_chat_tool_log", NEWEST_LOG_ROWS)        # filing, the decision and the checks behind it
    stills.save(page, "04b_chat_tool_log_whole", TOOL_LOG)
    stills.save(page, "05_chat_last_messages", LAST_MESSAGES)


def deck_stills(browser, base_url, claim_id, stills):
    """The stills that only need the claims log: the status page, the Claim file, the dashboard top and the
    workflow diagram on the home page."""
    context = browser.new_context(viewport={"width": PAGE["width"], "height": 1500}, device_scale_factor=2)
    page = context.new_page()
    card = "one('[class*=\"st-key-card-status\"]')"
    if stills.wants("status"):
        page.goto(f"{base_url}/status?claim={claim_id}", wait_until="networkidle")
        page.locator(".ca-status").wait_for()
        page.wait_for_timeout(3500)
        how = f"one('.ca-ai', {card}) || all('p.ca-small', {card}).find(p => p.querySelector('b'))"   # how it was decided
        stills.save(page, "06_status_card", f"one('.ca-status'), {how}")
        stills.save(page, "07_status_amount", f"section({card}, 'The amount', 'Your claim')")
        phone = browser.new_context(viewport={"width": 430, "height": 1500}, device_scale_factor=2).new_page()
        phone.goto(f"{base_url}/status?claim={claim_id}", wait_until="networkidle")
        phone.locator(".ca-status").wait_for()
        phone.wait_for_timeout(3500)
        stills.save(phone, "08_status_width_430", f"one('.ca-status'), section({card}, 'What happens next', 'Your claim')")
        phone.context.close()
    if stills.wants("file") or stills.wants("dashboard"):
        page.goto(f"{base_url}/dashboard", wait_until="networkidle")
        page.locator('[class*="st-key-card-claim-file"]').wait_for(timeout=60_000)
        page.wait_for_timeout(3000)
    if stills.wants("file"):
        box = page.locator('[class*="st-key-card-claim-file"] input[role="combobox"]')
        for attempt in range(4):                                   # the list closes if the page reruns meanwhile
            box.click()
            box.fill(claim_id)
            try:
                page.get_by_role("option").first.click(timeout=6000)
                break
            except Exception:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1500)
        page.wait_for_timeout(4000)
        file = "one('[class*=\"st-key-card-claim-file\"]')"
        # one column of the card, from its heading to its last line (the two columns differ in length)
        column = lambda title: (f"section(heading({file}, '{title}').closest('[data-testid=\"stColumn\"]'), "   # noqa: E731
                                f"'{title}')")
        stills.save(page, "09_file_what_the_customer_sent", column("What the customer sent"))
        stills.save(page, "10_file_the_rules", column("The rules"))
        stills.save(page, "11_file_fraud_check", f"section({file}, 'Fraud check', 'Damage and price')")
        stills.save(page, "12_file_damage_and_price", f"section({file}, 'Damage and price')")
    if stills.wants("dashboard"):
        stills.save(page, "13_dashboard_headline_figures",
                    "one('.ca-titlebar'), one('[class*=\"st-key-dash-filters\"]'), one('.ca-kpis')")
    if stills.wants("home"):
        page.goto(f"{base_url}/", wait_until="networkidle")
        page.locator(".ca-flow svg").wait_for(timeout=60_000)
        page.wait_for_timeout(7000)                                # the diagram has drawn itself
        stills.save(page, "14_home_workflow_section", "one('[class*=\"st-key-band-night-decide\"]')", pad=0)
        stills.save(page, "15_home_workflow_diagram", "one('.ca-flow')", pad=24)
    context.close()


# --- The numbers of one claim, read from the claims log -----------------------------------------------------------
def write_run_json(claim_id, folder, window=None):
    """Every value comes from data/runtime/claims.db; the split of the model cost comes from the spend log
    (data/runtime/spend.db), for the calls made between the start and the end of the run."""
    with sqlite3.connect(RUNTIME / "claims.db") as conn:
        conn.row_factory = sqlite3.Row
        row = dict(conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone())
    details = json.loads(row["details"])
    damage, estimate = details.get("damage") or {}, details.get("estimate") or {}
    fraud, decision = details.get("fraud") or {}, details.get("decision") or {}
    if window is None:                                            # from the log: chat start to a minute after filing
        filed = datetime.fromisoformat(row["filed_at"])
        window = ((filed - timedelta(seconds=(row["seconds_to_file"] or 0) + 2)).isoformat(timespec="seconds"),
                  (filed + timedelta(seconds=60)).isoformat(timespec="seconds"))
    with sqlite3.connect(RUNTIME / "spend.db") as conn:
        calls = conn.execute("SELECT prompt, model, cost_eur FROM spend WHERE at >= ? AND at <= ?", window).fetchall()
    by_prompt = {}
    for prompt, model, cost in calls:
        entry = by_prompt.setdefault(prompt, {"model": model, "calls": 0, "cost_eur": 0.0})
        entry["calls"] += 1
        entry["cost_eur"] += cost
    total = sum(e["cost_eur"] for e in by_prompt.values())           # rounded once, at the end
    chat_cost = sum(e["cost_eur"] for name, e in by_prompt.items() if name == "chat")
    for entry in by_prompt.values():
        entry["cost_eur"] = round(entry["cost_eur"], 5)
    run = {
        "claim_id": row["claim_id"], "filed_at": row["filed_at"], "channel": row["channel"],
        "policy_number": row["policy_number"], "status": row["status"], "decision": row["decision"],
        "customer_message": decision.get("customer_message"),
        "parts": [{"part": p["part"], "severity": p["severity"], "repair_or_replace": p.get("action")}
                  for p in damage.get("damaged_parts") or []],
        "estimate": {key: estimate.get(key) for key in ("lines", "unpriced_parts", "subtotal_ex_vat_eur", "vat_eur",
                                                        "gross_eur", "uses_placeholder_prices")},
        "estimate_eur": row["estimate_eur"], "deductible_eur": estimate.get("deductible_eur"),
        "estimate_after_deductible_eur": estimate.get("payout_eur"), "payout_eur": row["payout_eur"],
        "rule_checks": decision.get("checks"), "failed_rules": decision.get("reasons"),
        "confidence": row["confidence"], "confidence_reason": damage.get("confidence_reason"),
        "three_looks": ({"estimates_eur": damage["looks"], "confidences": damage.get("look_confidences")}
                        if damage.get("looks") else None),
        "fraud": {"risk": row["fraud_risk"], "points": fraud.get("points"),
                  "signals": [{k: s.get(k) for k in ("code", "points", "detail")} for s in fraud.get("signals") or []]},
        "seconds_confirm_to_decision": row["processing_seconds"], "seconds_start_to_filed": row["seconds_to_file"],
        "customer_messages": row["chat_turns"], "photo_retakes": row["photo_retakes"],
        "model_cost_eur": {
            "chat": round(chat_cost, 5), "checks": round(total - chat_cost, 5), "total": round(total, 5),
            "by_prompt": by_prompt,
            "in_claims_log_at_filing": row["api_cost_eur"], "calls_counted_from": window[0], "calls_counted_to": window[1],
        },
        "sources": {"claim": "data/runtime/claims.db, table claims", "model_cost_eur": "data/runtime/spend.db, table spend",
                    "note": "chat = the chat model's turns; checks = photo checks, damage assessment and fraud review. "
                            "in_claims_log_at_filing leaves out the chat turn that explains the decision afterwards. "
                            "payout_eur is what was paid (empty while a claims handler decides); "
                            "estimate_after_deductible_eur is the estimate minus the deductible. "
                            "three_looks are listed from low to high, not in the order they were made."},
    }
    path = Path(folder) / "run.json"
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  numbers {path}")
    return run


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
    """Reply to whatever the assistant just asked. Returns False once the confirm button is showing, or once the
    chat has been handed to a person."""
    if page.get_by_role("button", name="Confirm and file").count():
        return False
    if page.get_by_role("button", name="View your claim status").count():
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


def record_chat(page, base_url, story, stills=None):
    """Returns (claim id, the moment the recording should end). Stills of the chat are taken on the way: what is
    on screen during the recording, the rest after the part of the recording we keep."""
    chat_stills = stills is not None and stills.wants("chat")
    page.goto(f"{base_url}/chat?demo=1", wait_until="networkidle")
    page.locator('[class*="st-key-msg-assistant"]').first.wait_for()
    page.wait_for_timeout(1500)
    page.locator('[class*="st-key-sidepanel"] [data-testid="stSelectbox"]').click()
    page.get_by_role("option", name=story["label"]).click()
    page.wait_for_timeout(800)
    frame_chat(page)
    checklist_saved = False
    for _ in range(18):
        more = answer(page, story)
        if chat_stills and not checklist_saved and photos_accepted(page) >= 3:
            stills.save(page, "02_chat_checklist", CHECKLIST, fit=False)      # all three photos accepted
            checklist_saved = True
        if not more:
            break
    page.wait_for_timeout(1500)
    if page.get_by_role("button", name="Confirm and file").count():
        scroll_to(page, '[class*="st-key-card-confirm"]', offset=110, wait=2200)   # the summary to confirm
        if chat_stills:
            stills.save(page, "03_chat_confirm_card", CONFIRM_CARD, fit=False)
        page.get_by_role("button", name="Confirm and file").click()   # the 3D loader runs while the claim is checked
        page.get_by_role("button", name="View your claim status").wait_for(timeout=240_000)
        frame_chat(page)
        page.wait_for_timeout(4000)                            # the assistant explains the decision
    page.get_by_role("button", name="View your claim status").click()
    page.wait_for_url("**/status?claim=*", timeout=60_000)
    page.wait_for_timeout(2500)
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(3000)
    claim_id, end = re.search(r"claim=([A-Z0-9-]+)", page.url).group(1), time.time()
    if chat_stills:
        chat_stills_afterwards(page, stills)
    return claim_id, end


def record_form(page, base_url, story, stills=None):
    page.goto(f"{base_url}/claim?demo=1", wait_until="networkidle")
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
    return re.search(r"claim=([A-Z0-9-]+)", page.url).group(1), None


def record_dashboard(page, base_url, story, stills=None):
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
    scroll_to(page, '[class*="st-key-card-claim-file"]', wait=3500)   # the newest claim: every rule and why
    scroll_to(page, '[class*="st-key-card-claim-file"] .ca-table', offset=140, wait=3500)
    return None, None


FLOWS = {"chat": record_chat, "form": record_form, "dashboard": record_dashboard}


def spend_between(start, end):
    with sqlite3.connect(RUNTIME / "spend.db") as conn:
        return conn.execute("SELECT COALESCE(SUM(cost_eur), 0), COUNT(*) FROM spend WHERE at >= ? AND at <= ?",
                            (start, end)).fetchone()


def record(base_url, flow, set_name, video_dir, stills=None):
    """Runs one flow. Returns (raw video or None, seconds of it to keep or None, claim id or None)."""
    story = json.loads((ROOT / "data" / "demo_photos" / set_name / "claim.json").read_text())
    started_at = datetime.now().isoformat(timespec="seconds")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        video = {"record_video_dir": str(video_dir), "record_video_size": PAGE} if video_dir else {}
        context = browser.new_context(viewport=PAGE, device_scale_factor=2 if stills else 1, **video)
        page = context.new_page()
        started = time.time()
        claim_id, end = FLOWS[flow](page, base_url, story, stills)
        raw = page.video.path() if video_dir else None
        context.close()
        ended_at = (datetime.now() + timedelta(seconds=1)).isoformat(timespec="seconds")
        if stills and claim_id:
            deck_stills(browser, base_url, claim_id, stills)
            write_run_json(claim_id, stills.folder, (started_at, ended_at))
        browser.close()
    cost, calls = spend_between(started_at, ended_at)
    print(f"Model cost of this run: \u20ac{cost:.4f} ({calls} calls)" + (f", claim {claim_id}" if claim_id else ""))
    return (Path(raw) if raw else None), (end - started if end else None), claim_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flow", choices=[*FLOWS, "stills"], default="chat")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--set", default="small_clean")
    parser.add_argument("--out", help="default: static/demo_<flow>.mp4")
    parser.add_argument("--stills", help="chat flow: also save stills and run.json into this folder")
    parser.add_argument("--parts", default=",".join(PARTS), help=f"which stills: {', '.join(PARTS)}")
    parser.add_argument("--no-video", action="store_true", help="with --stills: don't save a video")
    parser.add_argument("--claim", help="with --flow stills: a claim already in the log")
    args = parser.parse_args()
    stills = Stills(args.stills, args.parts.split(",")) if args.stills else None

    if args.flow == "stills":                                     # no run: stills and numbers of a filed claim
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            deck_stills(browser, args.url, args.claim, stills)
            browser.close()
        if stills.wants("status") or stills.wants("file"):          # the parts that are about this one claim
            write_run_json(args.claim, stills.folder)
        return

    out = Path(args.out or ROOT / "static" / f"demo_{args.flow}.mp4")
    ffmpeg = shutil.which("ffmpeg") or "/opt/anaconda3/bin/ffmpeg"
    with tempfile.TemporaryDirectory() as tmp:
        raw, keep, _ = record(args.url, args.flow, args.set, None if args.no_video else Path(tmp), stills)
        if raw is None:
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        trim = ["-t", f"{keep:.2f}"] if keep else []                 # stills taken afterwards stay out of the video
        shown = f"crop={VIEWPORT['width']}:{VIEWPORT['height']}:0:0,scale=1280:-2"      # without the grey strip
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), *trim, "-vf", shown,
                        "-c:v", "libx264", "-preset", "slow", "-crf", "26", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", "-an", str(out)], check=True)
    poster = out.with_name(out.stem + "_poster.jpg")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "3", "-i", str(out), "-frames:v", "1", "-q:v", "3",
                    str(poster)], check=True)
    print(f"Saved {out} ({out.stat().st_size / 1e6:.1f} MB) and {poster.name}")


if __name__ == "__main__":
    main()
