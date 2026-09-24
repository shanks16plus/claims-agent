"""The one place that talks to AI models. Tracks tokens and cost, and never crashes on bad JSON.
Claude model IDs go to the Anthropic API; IDs with a "/" (e.g. qwen/qwen3.8-flash) go to OpenRouter."""
import json
import re
import threading
from dataclasses import dataclass, field

import anthropic
import openai

from core import config, storage

FALLBACK_BETA = "server-side-fallback-2026-07-01"
OPENROUTER_URL = "https://openrouter.ai/api/v1"

_clients = {}


class LLMError(Exception):
    pass


@dataclass
class Usage:
    """Running total of tokens and cost for one claim."""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: float = 0.0
    calls: int = 0
    json_retries: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, input_tokens, output_tokens, cost_usd):
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.cost_eur += cost_usd * config.USD_TO_EUR
            self.calls += 1



def _claude_cost(model, api_usage):
    """(input tokens, output tokens, cost in USD) for one direct Anthropic call."""
    fresh = api_usage.input_tokens or 0
    cache_write = getattr(api_usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(api_usage, "cache_read_input_tokens", 0) or 0
    out = api_usage.output_tokens or 0
    price = config.CLAUDE_USD_PER_MTOK.get(model, config.CLAUDE_USD_PER_MTOK["claude-opus-5-5"])
    usd = (fresh * price["input"] + cache_write * price["cache_write"]
           + cache_read * price["cache_read"] + out * price["output"]) / 1_000_000
    return fresh + cache_write + cache_read, out, usd


def check_budget():
    spent = storage.total_spend()
    if spent >= config.SPEND_LIMIT_EUR:
        raise LLMError(f"Spending limit reached (€{spent:.2f} of €{config.SPEND_LIMIT_EUR:.2f}). "
                       "Raise SPEND_LIMIT_EUR in core/config.py to continue.")


def _record(usage, model, prompt, input_tokens, output_tokens, cost_usd):
    """Add one call to the claim's usage and to the global spend log."""
    if usage is not None:
        usage.add(input_tokens, output_tokens, cost_usd)
    storage.log_spend(model, prompt, cost_usd * config.USD_TO_EUR)


def is_openrouter(model):
    return "/" in (model or "")


def _anthropic():
    if "anthropic" not in _clients:
        if not config.ANTHROPIC_API_KEY:
            raise LLMError("No ANTHROPIC_API_KEY found. Add it to .env (see .env.example).")
        _clients["anthropic"] = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _clients["anthropic"]


def _openrouter():
    if "openrouter" not in _clients:
        if not config.OPENROUTER_API_KEY:
            raise LLMError("No OPENROUTER_API_KEY found. Add it to .env (see .env.example).")
        # A stuck provider fails after 2 minutes instead of blocking a batch for 10.
        _clients["openrouter"] = openai.OpenAI(base_url=OPENROUTER_URL, api_key=config.OPENROUTER_API_KEY,
                                               timeout=120, max_retries=1)
    return _clients["openrouter"]


def load_prompt(name):
    return (config.PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def _supports_effort(model):
    return "haiku" not in model  # Haiku 4.5 has no effort setting; we run it without thinking


def _supports_fallback(model):
    return model.startswith(("claude-opus-5", "claude-fable"))


def create(model, usage=None, effort=None, prompt="chat", **params):
    """Send one request to Claude directly and add its cost to `usage`."""
    if not model:
        raise LLMError("No Claude model set. Add CLAUDE_MODEL to .env (see .env.example).")
    check_budget()
    params["model"] = model
    if effort and _supports_effort(model):
        params.setdefault("output_config", {})["effort"] = effort
    if config.USE_REFUSAL_FALLBACK and _supports_fallback(model):
        params["betas"] = [FALLBACK_BETA]
        params["fallbacks"] = "default"
    response = _anthropic().beta.messages.create(**params)
    _record(usage, model, prompt, *_claude_cost(model, response.usage))
    return response


def friendly_error(exc):
    if isinstance(exc, LLMError):
        return str(exc)
    if isinstance(exc, (anthropic.AuthenticationError, openai.AuthenticationError)):
        return "The API key was rejected. Check the key in .env."
    if isinstance(exc, (anthropic.RateLimitError, openai.RateLimitError)):
        return "Rate limit reached. Wait a minute and try again."
    if isinstance(exc, (anthropic.APIStatusError, openai.APIStatusError)):
        return f"API error {exc.status_code}: {exc.message}"
    if isinstance(exc, (anthropic.APIConnectionError, openai.APIConnectionError)):
        return "Could not reach the API. Check the internet connection."
    return f"Unexpected error: {exc}"


def parse_json(text):
    """Parse JSON, or pull the first {...} block out of surrounding text. None if impossible."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def ask_json(prompt_name, content, schema, effort, usage=None, max_tokens=16000, model=None):
    """Ask a model for JSON matching `schema`. Returns (data, error); exactly one is None.
    An unreadable answer is retried once; the retry is counted in usage.json_retries."""
    model = model or config.CLAUDE_MODEL
    ask = _ask_openrouter if is_openrouter(model) else _ask_claude
    for attempt in range(2):
        try:
            text = ask(model, prompt_name, content, schema, effort, usage, max_tokens)
        except (LLMError, anthropic.APIError, openai.APIError) as exc:
            return None, friendly_error(exc)
        data = parse_json(text)
        if isinstance(data, dict):
            return data, None
        if usage is not None and attempt == 0:
            usage.json_retries += 1
    return None, "The model did not return valid JSON, twice."


def _ask_claude(model, prompt_name, content, schema, effort, usage, max_tokens):
    response = create(
        model, usage, effort, prompt_name,
        max_tokens=max_tokens,
        system=load_prompt(prompt_name),
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "refusal":
        raise LLMError("The model declined to process this request.")
    if response.stop_reason == "max_tokens":
        raise LLMError("The model's answer was cut off before it finished.")
    return "".join(block.text for block in response.content if block.type == "text")


def _to_openai_content(content):
    """Convert Anthropic-style text and image blocks to the OpenAI format OpenRouter uses."""
    converted = []
    for block in content:
        if block["type"] == "text":
            converted.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image":
            source = block["source"]
            url = f"data:{source['media_type']};base64,{source['data']}"
            converted.append({"type": "image_url", "image_url": {"url": url}})
    return converted


def _ask_openrouter(model, prompt_name, content, schema, effort, usage, max_tokens):
    # Only route to providers that support images and structured output.
    extra = {"provider": {"require_parameters": True}}
    if effort and _supports_effort(model):
        extra["reasoning"] = {"effort": effort}
    check_budget()
    response = _openrouter().chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": load_prompt(prompt_name)},
            {"role": "user", "content": _to_openai_content(content)},
        ],
        response_format={"type": "json_schema",
                         "json_schema": {"name": prompt_name, "strict": True, "schema": schema}},
        extra_body=extra,
    )
    if response.usage:
        cost_usd = float((response.usage.model_extra or {}).get("cost") or 0.0)
        _record(usage, model, prompt_name, response.usage.prompt_tokens or 0,
                response.usage.completion_tokens or 0, cost_usd)
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise LLMError("The model's answer was cut off before it finished.")
    if choice.finish_reason == "content_filter":
        raise LLMError("The model declined to process this request.")
    return choice.message.content or ""
