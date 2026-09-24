"""Photo handling: the few metadata fields we need, clean copies without GPS, perceptual hashes."""
import base64
import io
from pathlib import Path

import imagehash
from PIL import Image, ImageOps

from core import config

EXIF_SUB_IFD = 0x8769
TAG_SOFTWARE, TAG_MAKE, TAG_MODEL, TAG_DATETIME, TAG_DATETIME_ORIGINAL = 305, 271, 272, 306, 36867


def _open(source):
    if isinstance(source, (bytes, bytearray)):
        return Image.open(io.BytesIO(source))
    return Image.open(source)


def read_metadata(source):
    """Return only software, camera and capture time. GPS is never read or stored."""
    img = _open(source)
    exif = img.getexif()
    sub = exif.get_ifd(EXIF_SUB_IFD) if exif else {}
    software = exif.get(TAG_SOFTWARE) or img.info.get("Software") or ""
    camera = f"{exif.get(TAG_MAKE, '')} {exif.get(TAG_MODEL, '')}".strip()
    taken_at = sub.get(TAG_DATETIME_ORIGINAL) or exif.get(TAG_DATETIME) or ""
    return {
        "has_metadata": bool(camera or taken_at or software),
        "software": str(software).strip(),
        "camera": camera,
        "taken_at": str(taken_at),
    }


def _prepared(source):
    """Upright, RGB, resized. Saving this drops all metadata, including GPS."""
    img = ImageOps.exif_transpose(_open(source)).convert("RGB")
    img.thumbnail((config.MAX_IMAGE_SIDE, config.MAX_IMAGE_SIDE))
    return img


def save_clean_copy(source, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _prepared(source).save(dest, "JPEG", quality=90)
    return dest


def image_block(path):
    """A photo as a Claude image content block."""
    buffer = io.BytesIO()
    _prepared(path).save(buffer, "JPEG", quality=90)
    data = base64.standard_b64encode(buffer.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def photo_hash(path):
    return str(imagehash.phash(_prepared(path)))


def hash_distance(hash_a, hash_b):
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
