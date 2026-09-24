"""The claim checklist, shared by chat, form and batch.
The assistant may only ask for these items, and a claim can only be filed when all required ones are in."""
import time

from core import config

REQUIRED_FIELDS = {
    "policy_number": "Policy number",
    "what_happened": "What happened",
    "incident_date": "Date of the incident",
    "incident_place": "Place of the incident",
    "other_party_involved": "Was another car involved?",
    "drivable": "Can the car still be driven?",
}
REQUIRED_PHOTOS = ["wide", "closeup", "plate"]
OPTIONAL_DOCUMENTS = {
    "repair_quote": "Repair quote from a garage",
    "police_report": "Police report (when another party was involved)",
}

# Situations the agent must not handle. Any of these sends the claim to a human.
SCOPE_FLAGS = {
    "injury": "Someone was injured",
    "theft": "Theft or attempted theft",
    "total_loss": "The car may be a total loss",
    "dispute": "Dispute with another driver about what happened",
    "upset_customer": "The customer is upset",
    "asked_for_human": "The customer asked for a person",
    "off_topic_repeated": "Repeated off-topic messages",
    "message_limit": "Message limit reached",
}


def new_claim(channel, language="en"):
    return {
        "claim_id": None,
        "channel": channel,               # chat, form or batch
        "language": language,             # en or nl
        **{field: None for field in REQUIRED_FIELDS},
        "photos": [],                     # {"slot", "name", "path", "usable", "metadata"}
        "documents": [],                  # {"kind", "name", "path"}
        "scope_flags": [],
        "confirmed": False,
        "summary": "",
        "source_key": None,               # groups re-runs of the same demo or test case
        "metrics": {"started_at": time.time(), "chat_turns": 0, "photo_retakes": 0},
    }


def guess_slot(filename):
    """Slot from a file name: wide*, plate*, anything else counts as a close-up."""
    name = filename.lower()
    if "wide" in name:
        return "wide"
    if "plate" in name:
        return "plate"
    return "closeup"


def usable_photos(claim):
    return [photo for photo in claim["photos"] if photo.get("usable", True)]


def missing_items(claim):
    """Labels of everything still needed before the claim can be filed."""
    missing = [label for field, label in REQUIRED_FIELDS.items() if claim.get(field) in (None, "")]
    slots = {photo["slot"] for photo in usable_photos(claim)}
    missing += [f"Photo: {config.PHOTO_SLOTS[slot]}" for slot in REQUIRED_PHOTOS if slot not in slots]
    return missing


def plain_summary(claim):
    """A readable summary built from the checklist fields, used when there is no chat summary."""
    yes_no = {True: "yes", False: "no", None: "unknown"}
    lines = [
        f"Policy: {claim['policy_number']}",
        f"Date and place: {claim['incident_date']}, {claim['incident_place']}",
        f"What happened: {claim['what_happened']}",
        f"Other car involved: {yes_no.get(claim['other_party_involved'], claim['other_party_involved'])}",
        f"Car drivable: {yes_no.get(claim['drivable'], claim['drivable'])}",
        f"Photos: {len(usable_photos(claim))}, documents: {len(claim['documents'])}",
    ]
    return "\n".join(lines)
