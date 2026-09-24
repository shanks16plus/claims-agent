"""The claim form: same checklist and tools as the chat, one step at a time."""
import json
import uuid
from datetime import date

import streamlit as st

from core import checklist, config, demo, images, llm
from core.pipeline import process_claim
from core.tools.check_photo_quality import check_photo_quality
from core.tools.lookup_policy import lookup_policy
from ui import theme

STEPS = ["Your details", "Photos", "Check and send"]
SCOPE_QUESTIONS = {
    "injury": "Someone was injured",
    "theft": "The car was stolen, or someone tried to steal it",
    "dispute": "I disagree with the other driver about what happened",
}
SLOT_HELP = {
    "wide": "Stand a few steps back so the whole car is in the photo, or at least the whole damaged side.",
    "closeup": "Get close to each damaged area. Add one photo per area.",
    "plate": "A straight-on photo where the number plate is easy to read.",
}
PHOTO_TYPES = ["jpg", "jpeg", "png", "webp"]
state = st.session_state


def reset():
    state.claim = checklist.new_claim("form")
    state.step = 0
    state.raw = {}                # photo key -> stored photo, before its check
    state.checked = {}            # photo key -> photo with its quality check
    state.photo_keys = []         # photos currently in the claim, in order
    state.upload_round = {slot: 0 for slot in config.PHOTO_SLOTS}
    state.usage = llm.Usage()
    state.upload_dir = config.RUNTIME / "uploads" / uuid.uuid4().hex[:12]


if "claim" not in state:
    reset()
claim = state.claim


def add_photo(key, photo):
    """Add a photo to the claim. A new wide shot or plate photo replaces the previous one."""
    if photo["slot"] != "closeup":
        state.photo_keys = [k for k in state.photo_keys if state.raw[k]["slot"] != photo["slot"]]
    state.raw[key] = photo
    state.photo_keys.append(key)


def checked_photo(key, photo):
    """Run the photo check once per photo and remember the result."""
    if key not in state.checked:
        with st.spinner("Checking your photo…"):
            result = check_photo_quality(photo["path"], photo["slot"], claim["language"], state.usage)
        photo = {**photo, "usable": result["usable"], "check": result}
        if not result["usable"]:
            claim["metrics"]["photo_retakes"] += 1
        state.checked[key] = photo
    return state.checked[key]


def show_check(photo):
    check = photo["check"]
    if photo["usable"]:
        note = "Looks good" if check.get("checked") else "Received (automatic check unavailable)"
        st.markdown(f"<p class='ca-check ok'>{note}</p>", unsafe_allow_html=True)
    else:
        hint = check.get("retake_hint") or "This photo can't be used. Please take it again."
        st.markdown(f"<p class='ca-check retake'>{hint}</p>", unsafe_allow_html=True)


# --- Header ------------------------------------------------------------------
theme.eyebrow("File a claim")
st.markdown("# " + ["Tell us what happened", "Add your photos", "Check and send"][state.step])
theme.steps(STEPS, state.step)


# --- Step 1: details ------------------------------------------------------------
def details_step():
    form_col, _, image_col = st.columns([12, 1, 8])
    with image_col:
        theme.photo("form", height=520, crop="center")
    with form_col:
        sets = demo.list_sets()
        if sets:
            with st.expander("Demo: fill in a ready-made claim"):
                choice = st.selectbox("Demo claim", list(sets), format_func=sets.get, label_visibility="collapsed")
                if st.button("Use this demo claim"):
                    story, photos = demo.load_set(choice)
                    claim.update({k: story[k] for k in checklist.REQUIRED_FIELDS if k in story})
                    claim["incident_date"] = claim["incident_date"] or date.today().isoformat()
                    state.photo_keys = []
                    for photo in photos:
                        add_photo(f"demo:{photo['path']}", photo)
                    claim["source_key"] = f"demo:{choice}"
                    st.rerun()
        with st.expander("Demo policy numbers"):
            policies = json.loads((config.DATA / "policies.json").read_text())["policies"]
            st.markdown("\n".join(f"- `{p['policy_number']}`: {p['demo_use']}" for p in policies))

        with st.form("details", border=False):
            policy_number = st.text_input("Policy number", value=claim["policy_number"] or "",
                                          placeholder="NL-100001")
            left, right = st.columns(2)
            incident_date = left.date_input(
                "Date of the incident", format="DD/MM/YYYY", max_value=date.today(),
                value=date.fromisoformat(claim["incident_date"]) if claim["incident_date"] else date.today())
            place = right.text_input("Where did it happen?", value=claim["incident_place"] or "",
                                     placeholder="Rotterdam, Nieuwe Binnenweg")
            what = st.text_area("What happened?", value=claim["what_happened"] or "", height=130,
                                placeholder="I was reversing out of a parking space and hit a bollard. "
                                            "The rear bumper is dented.")
            left, right = st.columns(2)
            other = left.radio("Was another car involved?", ["No", "Yes"], horizontal=True,
                               index=1 if claim["other_party_involved"] else 0)
            drivable = right.radio("Can the car still be driven?", ["Yes", "No"], horizontal=True,
                                   index=1 if claim["drivable"] is False else 0)
            st.markdown("<p style='margin:1rem 0 0.2rem;font-weight:600'>Does any of this apply?</p>",
                        unsafe_allow_html=True)
            flags = [key for key, label in SCOPE_QUESTIONS.items()
                     if st.checkbox(label, value=key in claim["scope_flags"])]
            language = st.radio("Messages about your claim in", ["English", "Nederlands"], horizontal=True,
                                index=1 if claim["language"] == "nl" else 0)
            submitted = st.form_submit_button("Continue to photos", type="primary")

        if submitted:
            problems = [label for label, value in [("your policy number", policy_number),
                                                   ("where it happened", place), ("what happened", what)]
                        if not value.strip()]
            if problems:
                st.error(f"Please add {', '.join(problems)}.")
                return
            if not lookup_policy(policy_number)["found"]:
                st.error(f"We can't find policy number {policy_number}. Check the number on your policy card.")
                return
            claim.update({
                "policy_number": policy_number.strip(),
                "incident_date": incident_date.isoformat(),
                "incident_place": place.strip(),
                "what_happened": what.strip(),
                "other_party_involved": other == "Yes",
                "drivable": drivable == "Yes",
                "scope_flags": flags,
                "language": "nl" if language == "Nederlands" else "en",
            })
            state.step = 1
            st.rerun()


# --- Step 2: photos ----------------------------------------------------------------
def photos_step():
    main, _, side = st.columns([12, 1, 7])
    with side:
        st.markdown("### Good photos help")
        st.markdown("<p class='ca-small'>Daylight or a well-lit place works best. Keep the phone steady, "
                    "and make sure the damage fills a good part of the close-up. We check each photo "
                    "as soon as you add it.</p>", unsafe_allow_html=True)
        if claim["scope_flags"]:
            st.markdown("<p class='ca-check retake'>Because of what you told us, a claims handler will "
                        "take over this claim. Photos still help them.</p>", unsafe_allow_html=True)

    with main:
        for slot, title in config.PHOTO_SLOTS.items():
            st.markdown(f"### {title}")
            st.markdown(f"<p class='ca-small'>{SLOT_HELP[slot]}</p>", unsafe_allow_html=True)
            kept = [k for k in state.photo_keys if state.raw[k]["slot"] == slot]
            for key in kept:
                photo = checked_photo(key, state.raw[key])
                image, note = st.columns([3, 4], vertical_alignment="center")
                image.image(photo["path"], width=240)
                with note:
                    show_check(photo)
                    if st.button("Remove", key=f"remove_{key}"):
                        state.photo_keys.remove(key)
                        st.rerun()
            has_usable = any(state.checked.get(k, {}).get("usable") for k in kept)
            if slot == "closeup" or not has_usable:
                label = "Add a photo" if not kept else "Add another photo" if slot == "closeup" else "Upload a retake"
                file = st.file_uploader(label, type=PHOTO_TYPES, key=f"upload_{slot}_{state.upload_round[slot]}")
                if file:
                    add_photo(f"upload:{file.file_id}",
                              images.store_upload(file.getvalue(), file.name, slot, state.upload_dir))
                    state.upload_round[slot] += 1      # a fresh, empty upload box
                    st.rerun()
            st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        photos = [state.checked[k] for k in state.photo_keys if k in state.checked]

        st.markdown("### Documents (optional)")
        kinds = ["repair_quote"] + (["police_report"] if claim["other_party_involved"] else [])
        documents = {d["kind"]: d for d in claim["documents"] if d["kind"] in kinds}
        for kind in kinds:
            label = checklist.OPTIONAL_DOCUMENTS[kind]
            if kind in documents:
                name, remove = st.columns([5, 2], vertical_alignment="center")
                name.markdown(f"<p class='ca-small'>{label}: <b>{documents[kind]['name']}</b></p>",
                              unsafe_allow_html=True)
                if remove.button("Remove", key=f"remove_doc_{kind}"):
                    documents.pop(kind)
                    claim["documents"] = list(documents.values())
                    st.rerun()
                continue
            file = st.file_uploader(label, type=["pdf"] + PHOTO_TYPES, key=f"doc_{kind}")
            if file:
                path = state.upload_dir / f"{kind}_{file.name}"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(file.getvalue())
                documents[kind] = {"kind": kind, "name": file.name, "path": str(path)}

        claim["photos"], claim["documents"] = photos, list(documents.values())
        missing = [m for m in checklist.missing_items(claim) if m.startswith("Photo")]
        back, forward, _ = st.columns([2, 3, 5])
        if back.button("Back"):
            state.step = 0
            st.rerun()
        if forward.button("Continue to check", type="primary"):
            if missing:
                st.error("We still need: " + ", ".join(m.replace("Photo: ", "").lower() for m in missing) + ".")
            else:
                state.step = 2
                st.rerun()


# --- Step 3: check and send ------------------------------------------------------------
def review_step():
    main, _, side = st.columns([12, 1, 8])
    with side:
        theme.photo("form", height=420, crop="center")
    with main:
        yes_no = {True: "Yes", False: "No"}
        applies = ", ".join(SCOPE_QUESTIONS[f] for f in claim["scope_flags"]) or "None"
        theme.key_values([
            ("Policy number", claim["policy_number"]),
            ("Date", date.fromisoformat(claim["incident_date"]).strftime("%d %B %Y")),
            ("Place", claim["incident_place"]),
            ("What happened", claim["what_happened"]),
            ("Another car involved", yes_no[claim["other_party_involved"]]),
            ("Car can be driven", yes_no[claim["drivable"]]),
            ("Also applies", applies),
            ("Documents", ", ".join(d["name"] for d in claim["documents"]) or "None"),
        ])
        usable = checklist.usable_photos(claim)
        st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
        st.image([p["path"] for p in usable], caption=[config.PHOTO_SLOTS[p["slot"]] for p in usable], width=170)

        left, right, _ = st.columns([3, 3, 4])
        if left.button("Edit details"):
            state.step = 0
            st.rerun()
        if right.button("Edit photos"):
            state.step = 1
            st.rerun()

        st.markdown("<div class='ca-rule' style='margin:1.5rem 0 1rem'></div>", unsafe_allow_html=True)
        confirmed = st.checkbox("I confirm these details are correct")
        if st.button("Send my claim", type="primary"):
            if not confirmed:
                st.error("Please confirm the details first.")
                return
            claim["confirmed"] = True
            with st.spinner("Checking your claim. This takes about half a minute."):
                _, filing = process_claim(claim, state.usage)
            if not filing["filed"]:
                st.error(filing["error"] + " " + ", ".join(filing.get("missing", [])))
                return
            claim_id = filing["claim_id"]
            reset()
            st.switch_page("views/claim_status.py", query_params={"claim": claim_id})


[details_step, photos_step, review_step][state.step]()
theme.footer()
