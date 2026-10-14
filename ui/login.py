"""Login page: one ID and password, set as APP_USERNAME / APP_PASSWORD in Secrets (or .env).

With neither set (e.g. running locally) the app is open. Wrong attempts are slowed down and, after several in a
row, locked for a minute in that browser session.
"""
import hmac
import time

import streamlit as st

from core.config import setting

MAX_TRIES, LOCK_SECONDS = 5, 60


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def require_login() -> bool:
    """True when the visitor may use the app; otherwise draws the login page."""
    user, pw = str(setting("APP_USERNAME") or ""), str(setting("APP_PASSWORD") or "")
    ss = st.session_state
    if not (user or pw) or ss.get("authed"):
        return True

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
        st.markdown("<div class='rr-banner' style='text-align:center'><h1>📄 Candor</h1>"
                    "<p>Tailored resumes. Every word true.</p></div>", unsafe_allow_html=True)
        locked = ss.get("login_locked_until", 0) - time.time()
        with st.form("login", border=True):
            st.subheader("Sign in")
            entered_user = st.text_input("ID", autocomplete="username")
            entered_pw = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch", disabled=locked > 0)
        if locked > 0:
            st.error(f"Too many wrong attempts. Try again in {int(locked) + 1} seconds.")
        elif submitted:
            if _same(entered_user.strip(), user) and _same(entered_pw, pw):
                ss.authed = True
                ss.login_fails = 0
                st.rerun()
            ss.login_fails = ss.get("login_fails", 0) + 1
            time.sleep(min(ss.login_fails, 3))  # slows down guessing
            if ss.login_fails >= MAX_TRIES:
                ss.login_locked_until, ss.login_fails = time.time() + LOCK_SECONDS, 0
                st.error(f"Too many wrong attempts. Try again in {LOCK_SECONDS} seconds.")
            else:
                st.error("Wrong ID or password.")
    return False


def logout_button() -> None:
    """Sidebar sign-out, shown only when a login is configured."""
    if setting("APP_USERNAME") or setting("APP_PASSWORD"):
        with st.sidebar:
            st.divider()
            if st.button("🚪 Sign out", width="stretch"):
                st.session_state.authed = False
                st.rerun()
