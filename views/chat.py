"""The claims assistant: a chat on the left, and on the right what the agent is doing behind the scenes
(checklist, every tool call and every guardrail), so an audience can watch it work."""
import html
import json
import time

import streamlit as st

from core import agent, checklist, config, demo
from ui import loaders, theme
from ui.theme import band, card, esc, lift, show

state = st.session_state
if "chat" not in state:
    state.chat = agent.Chat()
chat = state.chat


def short(value, limit=420):
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + " …"


def render_log(chat):
    if not chat.events:
        return "<p class='ca-empty'>No tool calls yet. They appear here as the assistant works.</p>"
    kinds = {"tool": "agent tool", "code": "fixed code", "guard": "guardrail"}
    rows = []
    for event in reversed(chat.events[-14:]):
        seconds = f"{event['seconds']:.1f} s" if event["seconds"] else event["at"]
        args = f"<pre class='args'>{html.escape(short(event['args'], 200))}</pre>" if event["args"] else ""
        result = f"<pre>{html.escape(short(event['result']))}</pre>" if event["result"] is not None else ""
        css = {"guard": " guard", "code": " code"}.get(event["kind"], "")
        rows.append(f"<div class='ca-log{css}'><div class='h'><b>{esc(event['name'])}</b>"
                    f"<span class='kind'>{kinds[event['kind']]}</span><span class='ms'>{seconds}</span></div>"
                    f"{args}{result}</div>")
    return "".join(rows)


def render_checklist(chat):
    claim, rows = chat.claim, []
    policy = claim["policy_number"] if chat.policy and chat.policy.get("found") else None
    values = {"policy_number": policy, **{f: claim.get(f) for f in checklist.REQUIRED_FIELDS if f != "policy_number"}}
    for field, label in checklist.REQUIRED_FIELDS.items():
        value = values[field]
        shown = {True: "Yes", False: "No"}.get(value, value) if value not in (None, "") else "Waiting"
        rows.append(f"<li class='{'filled' if value not in (None, '') else 'empty'}'><span>{esc(label)}</span>"
                    f"<em>{esc(shown)}</em></li>")
    usable = {p["slot"] for p in checklist.usable_photos(claim)}
    for slot, label in config.PHOTO_SLOTS.items():
        count = sum(p["slot"] == slot for p in checklist.usable_photos(claim))
        rows.append(f"<li class='{'filled' if slot in usable else 'empty'}'><span>{esc(label)}</span>"
                    f"<em>{f'{count} accepted' if count else 'Waiting'}</em></li>")
    docs = ", ".join(d["name"] for d in claim["documents"]) or "None yet (optional)"
    rows.append(f"<li class='{'filled' if claim['documents'] else 'empty'}'><span>Documents</span><em>{esc(docs)}</em></li>")
    return f"<ul class='ca-checklist'>{''.join(rows)}</ul>"


def render_meter(chat):
    return (f"<div class='ca-meter'><span>Messages {chat.customer_messages} / {config.MAX_CUSTOMER_MESSAGES}</span>"
            f"<span>Model cost €{chat.usage.cost_eur:.3f}</span></div>")


def message(role, text, photos=(), docs=(), index=0):
    with st.container(key=f"msg-{role}-{index}"):
        show(f"<p class='ca-who'>{'You' if role == 'customer' else 'Claims assistant'}</p>")
        if text:
            st.markdown(text)
        if photos:
            st.image(list(photos), width=120)
        if docs:
            show(f"<p class='ca-small'>Attached: {esc(', '.join(docs))}</p>")


# --- Page ----------------------------------------------------------------------------------------------------
overlay = st.container()          # top level, so the full-screen loader sits above everything
with band("hero-page", "chat"):
    theme.hero_media("phone")
    theme.heading("Claims assistant", "Report damage in a conversation", size="page-title")
    show("<p class='ca-lede' style='margin-top:.8rem'>The assistant asks one question at a time and checks your "
         "photos as you send them. You can ask for a person at any time.</p>")

with band("paper", "chat-body"), lift("chat"):
    left, right = st.columns([7, 5], gap="medium")

    # Behind the scenes: built first so the agent can update it while it works
    with right, st.container(key="sidepanel"):
        sets = demo.list_sets() if theme.demo_mode() else {}
        demo_send = None
        if sets and not chat.ended:
            show("<div class='ca-label'><b>Demo</b>Send ready-made photos</div>")
            choice = st.selectbox("Demo set", list(sets), format_func=sets.get, label_visibility="collapsed")
            story, demo_photos = demo.load_set(choice)
            by_slot = {}
            for p in demo_photos:
                by_slot.setdefault(p["slot"], p)
            show(f"<p class='ca-small' style='color:var(--on-dark-soft);margin:0'>Policy for this set: "
                 f"<span class='ca-mono'>{esc(story.get('policy_number', '-'))}</span></p>")
            with st.container(horizontal=True, gap="small"):
                if story.get("what_happened") and st.button("Story", key="demo_story"):
                    demo_send = (story["what_happened"], None, choice)
                for slot, label in [("wide", "Wide shot"), ("closeup", "Close-up"), ("plate", "Plate")]:
                    if slot in by_slot and st.button(label, key=f"demo_{slot}"):
                        demo_send = ("", by_slot[slot], choice)
        show("<div class='ca-label' style='margin-top:.6rem'><b>Live</b>Claim checklist</div>")
        checklist_box = st.empty()
        meter_box = st.empty()
        show("<div class='ca-label' style='margin-top:.6rem'><b>Log</b>Tool calls and guardrails, newest first</div>")
        log_box = st.empty()

    def refresh(chat):
        checklist_box.html(render_checklist(chat))
        meter_box.html(render_meter(chat))
        log_box.html(render_log(chat))

    refresh(chat)

    # The conversation
    with left:
        log = st.container(key="chatlog", height=640, autoscroll=True)
        with log:
            for i, turn in enumerate(chat.transcript):
                message(turn["role"], turn.get("text", ""), turn.get("photos", ()), turn.get("docs", ()), i)
        actions = st.container()
        typed = st.chat_input("This chat has ended" if chat.ended else "Type your answer, or add photos",
                              accept_file="multiple", file_type=["jpg", "jpeg", "png", "webp", "pdf"],
                              disabled=chat.ended, submit_mode="disable")

    # A new customer message: typed, with files, or from the demo buttons
    pending = None
    if typed is not None and not chat.ended:
        ids, shown_photos, shown_docs = [], [], []
        for file in typed.files or []:
            if file.name.lower().endswith(".pdf"):
                ids.append(agent.add_document(chat, file.getvalue(), file.name))
                shown_docs.append(file.name)
            else:
                photo_id = agent.add_photo(chat, data=file.getvalue(), name=file.name)
                ids.append(photo_id)
                shown_photos.append(chat.uploads[photo_id]["path"])
        pending = (typed.text or "", ids, shown_photos, shown_docs)
    elif demo_send is not None:
        text, demo_photo, set_name = demo_send
        chat.claim["source_key"] = f"demo:{set_name}"     # re-runs of a demo set aren't flagged as duplicates
        ids = [agent.add_photo(chat, photo=demo_photo)] if demo_photo else []
        pending = (text, ids, [demo_photo["path"]] if demo_photo else [], [])

    if pending:
        text, ids, shown_photos, shown_docs = pending
        chat.transcript.append({"role": "customer", "text": text, "photos": shown_photos, "docs": shown_docs})
        with log:
            message("customer", text, shown_photos, shown_docs, len(chat.transcript) - 1)
            thinking = st.empty()
            thinking.html("<div class='ca-who' style='margin-top:.6rem'>Claims assistant</div>"
                          "<span class='ca-skel' style='width:78%'></span><span class='ca-skel' style='width:62%'></span>"
                          "<span class='ca-skel' style='width:40%'></span>")
        agent.respond(chat, text, ids, on_event=refresh)
        st.rerun()

    # Under the conversation: confirmation, ending, or the offer of a person
    with actions:
        if chat.ready_to_file:
            with card("confirm"):
                show("<div class='ca-label' style='margin:0'><b>Check</b>Your claim before it is filed</div>")
                claim = chat.claim
                yes_no = {True: "Yes", False: "No"}
                theme.key_values([
                    ("Policy number", claim["policy_number"]),
                    ("Date", claim["incident_date"]),
                    ("Place", claim["incident_place"]),
                    ("What happened", claim["what_happened"]),
                    ("Another car involved", yes_no.get(claim["other_party_involved"], "-")),
                    ("Car can be driven", yes_no.get(claim["drivable"], "-")),
                    ("Photos", f"{len(checklist.usable_photos(claim))} accepted"),
                    ("Documents", ", ".join(d["name"] for d in claim["documents"]) or "None"),
                ])
                with st.container(horizontal=True, gap="small"):
                    confirm = st.button("Confirm and file", type="primary")
                    change = st.button("Change something")
            if change:
                chat.transcript.append({"role": "assistant", "text": "Of course. What would you like to change?"})
                chat.messages.append({"role": "assistant", "content": "Of course. What would you like to change?"})
                st.rerun()
            if confirm:
                run = loaders.ClaimRun(overlay, [p["path"] for p in checklist.usable_photos(chat.claim)])
                try:
                    agent.confirm_and_file(chat, progress=run, on_event=refresh)
                finally:
                    time.sleep(0.8)
                    run.clear()
                st.rerun()
        elif chat.ended:
            with st.container(horizontal=True, gap="small"):
                if st.button("View your claim status", type="primary"):
                    st.switch_page("views/claim_status.py", query_params={"claim": chat.filed["claim_id"]})
                if st.button("Start a new chat"):
                    del state.chat
                    st.rerun()
        elif chat.offer_person:
            show("<p class='ca-small' style='margin:.8rem 0 .4rem'>Would you rather talk to a person?</p>")
            if st.button("Pass me to a claims handler"):
                agent.hand_over(chat, "asked_for_human", on_event=refresh)
                st.rerun()

theme.footer()
