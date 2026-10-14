import streamlit as st

st.set_page_config(page_title="Candor · Honest resume tailoring", page_icon="📄", layout="wide")

from storage.db import make_store  # noqa: E402
from ui import history, login, redraft, settings_tab, sidebar, style, usage  # noqa: E402

style.apply()


@st.cache_resource
def get_store():
    return make_store()


if not login.require_login():
    st.stop()

store = get_store()
style.banner()
sidebar.render(store)
login.logout_button()
t_redraft, t_history, t_usage, t_settings = st.tabs(["✍️ Tailor", "🗂️ History", "📊 Usage", "⚙️ Settings"])
with t_redraft:
    redraft.render(store)
with t_history:
    history.render(store)
with t_usage:
    usage.render(store)
with t_settings:
    settings_tab.render(store)
