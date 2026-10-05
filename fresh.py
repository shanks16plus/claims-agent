"""Keeps a running server on the latest code.

Streamlit Cloud applies a push by reloading changed files in place, without restarting the app. That is not
enough for a line like `from ui import theme`: Python finds the old module still attached to its package and
keeps using it, so pages would run new code against old helpers until someone reboots the app. app.py calls
use_latest_code() before it imports anything of ours: when a file in our packages has changed, the packages are
dropped and imported again.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PACKAGES = ("core", "ui")
_seen = None        # newest change time of our source files at the last check


def use_latest_code():
    global _seen
    stamp = max(path.stat().st_mtime for name in PACKAGES for path in (ROOT / name).rglob("*.py"))
    if stamp != _seen:
        for module in [name for name in sys.modules if name.split(".")[0] in PACKAGES]:
            del sys.modules[module]
        _seen = stamp
