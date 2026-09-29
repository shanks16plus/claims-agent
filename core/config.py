"""All settings in one place. Business rules and prices live here, not in prompts."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RUNTIME = DATA / "runtime"
PROMPTS = ROOT / "prompts"

load_dotenv(ROOT / ".env")


def secret(name, default=None):
    """Read a setting from .env locally, or from Streamlit secrets when deployed."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except Exception:
        return default


# --- Models -----------------------------------------------------------------
ANTHROPIC_API_KEY = secret("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = secret("OPENROUTER_API_KEY")

# Strong model where accuracy matters, fast and cheap model for chat and photo checks.
# Damage assessment has its own setting: Kimi K3 was picked after the model comparison
# (similar results to Opus 5.5 at about a third of the cost).
CLAUDE_MODEL = secret("CLAUDE_MODEL")
CLAUDE_MODEL_FAST = secret("CLAUDE_MODEL_FAST") or CLAUDE_MODEL
ASSESS_MODEL = secret("ASSESS_MODEL") or CLAUDE_MODEL
# The chat assistant has its own setting: it needs reliable tool calls and quick replies, not vision.
CHAT_MODEL = secret("CHAT_MODEL") or CLAUDE_MODEL_FAST
MODEL_FOR = {
    "photo_quality": CLAUDE_MODEL_FAST,
    "assess_damage": ASSESS_MODEL,
    "fraud_review": CLAUDE_MODEL,
    "chat": CHAT_MODEL,
}

# Effort controls how long the model thinks (low / medium / high / xhigh / max).
# Not sent to Claude Haiku 4.5, which runs without thinking.
EFFORT = {
    "photo_quality": "low",
    "assess_damage": "medium",
    "fraud_review": "medium",
    "chat": "low",                  # short thinking keeps replies quick
}

# If Claude's safety filter declines a request, retry it on another Claude model.
USE_REFUSAL_FALLBACK = True

# Models for the damage-assessment head-to-head in the batch test.
# Claude IDs go to Anthropic directly, IDs with a "/" go through OpenRouter.
COMPARISON_MODELS = {
    "anthropic/claude-opus-5.5": "Claude Opus 5.5",
    "claude-opus-5-5": "Claude Opus 5.5 (Anthropic direct)",
    "qwen/qwen3.8-flash": "Qwen3.8 Flash",
    "z-ai/glm-5.3-flash": "GLM-5.3 Flash",
    "moonshotai/kimi-k3": "Kimi K3",
    "deepseek/deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
}
COMPARISON_DEFAULT = ["moonshotai/kimi-k3", "anthropic/claude-opus-5.5"]  # chosen model first

# --- Business rules (used by decide) ----------------------------------------
AUTO_SETTLE_MAX_EUR = 1500        # gross repair estimate must be below this
MIN_CONFIDENCE_AUTO = 0.80        # model confidence needed to settle automatically; calibrate with the batch test
TOTAL_LOSS_SHARE = 0.60           # estimate above this share of vehicle value -> human
VAT_RATE = 0.21                   # Dutch BTW, added on top of parts_prices.csv (ex VAT)

# Repair cost scales with severity. Placeholder factors, replace after testing.
SEVERITY_FACTOR = {"minor": 0.6, "moderate": 1.0, "severe": 1.5}

# Repair or replace is decided here, not by the model (it flipped between the two for the same bumper).
# A part is replaced from this severity up. Parts the price table can't repair (lights, side and rear
# windows, the grille) are always replaced.
REPLACE_FROM = {"windscreen": "moderate", "wing_mirror_left": "moderate", "wing_mirror_right": "moderate"}
REPLACE_FROM_DEFAULT = "severe"   # body panels, bumpers, wheels

# Near the auto-settle limit, one assessment isn't steady enough: the same photos moved by up to about €500
# between runs. When the first estimate is this close to the limit, the photos are assessed twice more and the
# middle estimate and the middle confidence of the three are used.
EXTRA_LOOKS_MARGIN_EUR = 500

# --- Fraud scoring ----------------------------------------------------------
# Each signal adds points. Total >= HIGH -> high risk, >= MEDIUM -> medium risk.
FRAUD_POINTS = {
    "ai_content_credentials": 4,    # the photo's own Content Credentials or metadata say it was made with AI
    "ai_detector_likely": 3,        # the AI-image detector is at least AI_DETECTOR_LIKELY sure
    "ai_detector_possible": 1,      # weak: at least AI_DETECTOR_POSSIBLE
    "duplicate_photo": 4,
    "incident_before_policy_start": 4,
    "editing_software": 3,
    "story_photo_mismatch": 3,
    "incident_in_future": 2,
    "story_photo_partial_mismatch": 1,
    "possible_manipulation": 1,     # AI judgement on edited / generated photos: weak signal
    "no_photo_metadata": 1,         # weak: messaging apps strip metadata too
    "policy_started_recently": 1,
}
FRAUD_HIGH = 4
FRAUD_MEDIUM = 2
DUPLICATE_MAX_DISTANCE = 6        # perceptual-hash distance that counts as "same photo"
AI_DETECTOR_LIKELY = 0.90         # Sightengine "ai_generated" score (0 to 1)
AI_DETECTOR_POSSIBLE = 0.60
# Optional AI-image detector (free tier at sightengine.com). Leave empty to skip it.
SIGHTENGINE_API_USER = secret("SIGHTENGINE_API_USER")
SIGHTENGINE_API_SECRET = secret("SIGHTENGINE_API_SECRET")
RECENT_POLICY_DAYS = 14
EDITING_SOFTWARE = [
    "photoshop", "lightroom", "gimp", "snapseed", "picsart", "canva", "affinity",
    "pixelmator", "facetune", "midjourney", "dall", "stable diffusion", "firefly",
]

# --- Chat guardrails ----------------------------------------------------------
MAX_CUSTOMER_MESSAGES = 25
MAX_OFF_TOPIC_IN_ROW = 2

# --- API cost in euro ---------------------------------------------------------
# Anthropic list prices in USD per million tokens, used when calling Anthropic directly.
# Through OpenRouter, the cost of each request comes back with the answer.
CLAUDE_USD_PER_MTOK = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
}
USD_TO_EUR = 0.88                 # approximate, fixed rate: update before the deck

# Hard stop: no new model calls once this much has been spent (logged in data/runtime/spend.db).
# A second safety net behind the credit limit on the OpenRouter key.
SPEND_LIMIT_EUR = 15.00

# --- Photos -------------------------------------------------------------------
MAX_IMAGE_SIDE = 1568             # longest side sent to Claude, in pixels
PHOTO_SLOTS = {
    "wide": "Wide shot of the whole car",
    "closeup": "Close-up of a damaged area",
    "plate": "Number plate",
}
