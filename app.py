import hmac

import streamlit as st

st.set_page_config(page_title="Resume Redrafter", page_icon="📄", layout="wide")

from core.config import setting  # noqa: E402
from storage.db import make_store  # noqa: E402
from ui import history, redraft, settings_tab, sidebar, style, usage  # noqa: E402

style.apply()


@st.cache_resource
def get_store():
    return make_store()


def password_gate() -> bool:
    """Optional: set APP_PASSWORD in secrets to protect a public deployment."""
    pw = setting("APP_PASSWORD")
    if not pw or st.session_state.get("authed"):
        return True
    st.title("📄 Resume Redrafter")
    entered = st.text_input("Password", type="password")
    if st.button("Enter"):
        if hmac.compare_digest(entered.encode(), str(pw).encode()):
            st.session_state.authed = True
            st.rerun()
        st.error("Wrong password.")
    return False


if not password_gate():
    st.stop()

store = get_store()
style.banner()
sidebar.render(store)
t_redraft, t_history, t_usage, t_settings = st.tabs(["✍️ Redraft", "🗂️ History", "📊 Usage", "⚙️ Settings"])
with t_redraft:
    redraft.render(store)
with t_history:
    history.render(store)
with t_usage:
    usage.render(store)
with t_settings:
    settings_tab.render(store)
