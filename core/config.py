import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)


def setting(name: str, default=None):
    """Read a setting from environment variables / .env first, then Streamlit secrets."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:  # no secrets.toml present
        return default
