import re

import streamlit as st

from core.tokens import price_for

INTENSITIES = ["Light", "Moderate", "Strong"]
INTENSITY_HELP = (
    "Light: headline, summary, skills order + ~30% of bullets reworded. "
    "Moderate: ~60% of bullets reworded and reordered. "
    "Strong: nearly every bullet reworded, reordered and tightened. Facts are locked at every level."
)


def model_label(model: str) -> str:
    price, exact = price_for(model)
    if not price:
        return f"{model}  ·  price unknown"
    approx = "" if exact else "≈"
    return f"{model}  ·  {approx}${price['input']:g} in / ${price['output']:g} out per 1M"


def record_usage(store, entries: list[dict], app_id=None, version_id=None, company=None) -> None:
    """Persist token usage (even for failed runs, since those tokens were still billed)."""
    if not entries:
        return
    st.session_state.setdefault("session_usage", []).extend(entries)
    try:
        store.log_usage(entries, app_id, version_id, company)
    except Exception as e:  # never lose the user's result because of a logging failure
        st.warning(f"Couldn't save usage log: {e}")


def safe_filename(*parts: str) -> str:
    name = "_".join(p for p in parts if p)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:120] or "resume"
