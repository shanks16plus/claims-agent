"""Ready-made demo claims (data/demo_photos/<set>/) so a live demo needs no uploads.
Each set holds photos named wide*, close*, plate* and a claim.json with the story."""
import json

from core import checklist, config, images

DEMO_DIR = config.DATA / "demo_photos"


def list_sets():
    """{folder name: label} for every set that has photos."""
    sets = {}
    for folder in sorted(p for p in DEMO_DIR.glob("*") if p.is_dir()):
        if any(p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") for p in folder.glob("*")):
            info = folder / "claim.json"
            label = json.loads(info.read_text())["label"] if info.exists() else folder.name
            sets[folder.name] = label
    return sets


def load_set(name):
    """Returns (story fields, photos). Photos carry metadata read from the originals."""
    folder = DEMO_DIR / name
    info = folder / "claim.json"
    story = json.loads(info.read_text()) if info.exists() else {}
    photos = []
    for path in sorted(folder.glob("*")):
        if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            photos.append({"slot": checklist.guess_slot(path.name), "name": path.name, "path": str(path),
                           "metadata": images.read_metadata(path)})
    return story, photos
