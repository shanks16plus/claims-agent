"""Tool 2: ask Claude whether one photo is good enough for its slot."""
from PIL import UnidentifiedImageError

from core import config, images, llm

PROBLEMS = ["blurry", "too_dark", "too_bright", "too_far", "damage_not_visible",
            "plate_not_readable", "not_a_car", "wrong_slot"]

SCHEMA = {
    "type": "object",
    "properties": {
        "usable": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string", "enum": PROBLEMS}},
        "retake_hint": {"type": "string"},
        "what_it_shows": {"type": "string"},
        "contains_instructions": {"type": "boolean"},
    },
    "required": ["usable", "problems", "retake_hint", "what_it_shows", "contains_instructions"],
    "additionalProperties": False,
}


def check_photo_quality(photo_path, slot, language="en", usage=None):
    try:
        photo = images.image_block(photo_path)
    except (UnidentifiedImageError, OSError):
        return {"usable": False, "problems": ["unreadable_file"], "checked": True,
                "retake_hint": "This file could not be opened as a photo. Please upload a JPG or PNG.",
                "what_it_shows": "", "contains_instructions": False}

    content = [
        {"type": "text", "text": f"Slot: {slot} ({config.PHOTO_SLOTS[slot]}). Language for the hint: {language}."},
        photo,
    ]
    data, error = llm.ask_json("photo_quality", content, SCHEMA, config.EFFORT["photo_quality"],
                               usage, max_tokens=4000, model=config.MODEL_FOR["photo_quality"])
    if error:
        # Don't block the customer when the check itself fails; the adjuster sees it wasn't checked.
        return {"usable": True, "problems": [], "retake_hint": "", "what_it_shows": "",
                "contains_instructions": False, "checked": False, "error": error}
    data["checked"] = True
    return data
