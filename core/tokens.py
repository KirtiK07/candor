"""Token counting and cost estimation."""
import json
from functools import lru_cache
from pathlib import Path

import tiktoken

PRICING_PATH = Path(__file__).resolve().parent.parent / "config" / "pricing.json"


def load_pricing() -> dict:
    try:
        return json.loads(PRICING_PATH.read_text(encoding="utf-8")).get("models", {})
    except (OSError, json.JSONDecodeError):
        return {}


def save_pricing(models: dict) -> None:
    try:
        data = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data["models"] = models
    PRICING_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def price_for(model: str, pricing: dict | None = None) -> tuple[dict | None, bool]:
    """Return (price, exact_match). Falls back to the longest matching prefix."""
    pricing = load_pricing() if pricing is None else pricing
    if model in pricing:
        return pricing[model], True
    matches = [k for k in pricing if model.startswith(k)]
    if not matches:
        return None, False
    return pricing[max(matches, key=len)], False


def cost(model: str, prompt_tokens: int, completion_tokens: int, pricing: dict | None = None) -> float | None:
    price, _ = price_for(model, pricing)
    if not price:
        return None
    return (prompt_tokens * price["input"] + completion_tokens * price["output"]) / 1_000_000


@lru_cache(maxsize=None)
def _encoding(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    return len(_encoding(model).encode(text)) if text else 0


def truncate_tokens(text: str, max_tokens: int, model: str = "gpt-4o") -> str:
    enc = _encoding(model)
    ids = enc.encode(text or "")
    return text if len(ids) <= max_tokens else enc.decode(ids[:max_tokens]) + "\n[...truncated]"


def estimate_run(resume_text: str, jd_text: str, model: str, cover_letter: bool, retry: bool = False) -> dict:
    """Rough estimate of the tokens one pipeline run will use (system prompts + JSON round trips)."""
    r = count_tokens(resume_text, model)
    j = count_tokens(jd_text, model)
    rj = int(r * 1.3)  # resume as JSON is a bit larger than plain text
    analysis = 900
    inp = out = 0
    if not retry:
        inp += 450 + r                      # extract resume
        out += rj
        inp += 550 + j + rj                 # JD analysis + gap
        out += analysis
    inp += 1100 + rj + analysis + 200       # rewrite
    out += int(rj * 1.1) + 700              # tailored resume + change log
    if retry:
        inp += rj + 150                     # previous draft + feedback
    inp += 700 + r + rj                     # fact check of every change
    out += 300
    inp += 400 + r                          # repair of flagged claims (only runs when something is flagged)
    out += 250
    if cover_letter:
        inp += 300 + rj + analysis
        out += 550
    return {"input": inp, "output": out, "cost": cost(model, inp, out)}
