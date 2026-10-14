import streamlit as st

from core.llm_client import (LLM, PROVIDERS, LLMError, api_key, available_providers, check_provider,
                             default_provider, probe_model)
from ui.common import model_label


@st.cache_data(ttl=3600, show_spinner="Checking your API key with a test request…")
def _check(provider: str, key: str) -> dict:
    """Cached per key: list models, run tiny test calls, choose a default. `key` is part of the cache key."""
    try:
        return check_provider(provider)
    except LLMError as e:
        return {"models": [], "probes": {}, "default": None, "failed": {}, "key_error": str(e)}


@st.cache_data(ttl=3600, show_spinner="Testing this model…")
def _probe(provider: str, key: str, model: str) -> dict:
    return probe_model(provider, key, model)


def _status(provider: str) -> dict:
    return _check(provider, api_key(provider))


def _choose_provider(providers: list[str]) -> str:
    """Default provider first; if its key fails the test, use the next one that works."""
    first = default_provider()
    for p in [first] + [p for p in providers if p != first]:
        if _status(p)["default"]:
            return p
    return first


def backup_chain(provider: str) -> list[tuple[str, str, int | None]]:
    """Every other provider whose key passed its test, with its verified default model, in priority order."""
    chain = []
    for p in available_providers():
        st_ = _status(p)
        if p != provider and st_["default"]:
            chain.append((p, st_["default"], st_["probes"][st_["default"]].get("tpm")))
    return chain


def make_llm(model: str) -> LLM:
    """LLM for the selected provider/model with its token limit and the verified backup chain."""
    ss = st.session_state
    probe = _status(ss.provider)["probes"].get(model) or _probe(ss.provider, api_key(ss.provider), model)
    return LLM(ss.provider, model, fallbacks=backup_chain(ss.provider), tpm=probe.get("tpm"))


def _label(provider: str, model: str) -> str:
    probe = _status(provider)["probes"].get(model)
    tag = ""
    if probe and probe.get("ok"):
        tag = "  ·  ✓ tested" + (f", {probe['tpm']:,} tok/min" if probe.get("tpm") else "")
    return model_label(model) + tag


def render(store) -> None:
    ss = st.session_state
    providers = available_providers()
    ss.model_ok = False
    with st.sidebar:
        st.subheader("🤖 AI provider & model")
        if not providers:
            ss.models, ss.provider = [], None
            st.error("No API key found. Add `GROQ_API_KEY=...` and/or `OPENAI_API_KEY=...` to the `.env` file "
                     "in the project folder (or to Secrets when deployed), then restart the app.")
        else:
            if ss.get("provider") not in providers:
                ss.provider = _choose_provider(providers)
            provider_labels = {p: PROVIDERS[p]["label"] + ("" if _status(p)["default"] else " ⚠️") for p in providers}
            st.radio("Provider", providers, key="provider", horizontal=True, format_func=provider_labels.get)
            status = _status(ss.provider)
            ss.models = status["models"]
            if status["key_error"] and not status["default"]:
                st.error(f"{status['key_error']}\n\nFix `{PROVIDERS[ss.provider]['env']}` in `.env`, or switch provider.")
            if ss.models:
                if ss.get("model") not in ss.models:
                    ss.model = status["default"] or ss.models[0]
                labels = {m: _label(ss.provider, m) for m in ss.models}
                st.selectbox("Model", ss.models, key="model", format_func=labels.get,
                             help="Pre-selected: the best model that passed a live test call with your key. "
                                  "Models that can't handle a resume (e.g. tiny output limits) are hidden.")
                probe = status["probes"].get(ss.model) or _probe(ss.provider, api_key(ss.provider), ss.model)
                ss.model_ok, ss.model_tpm = probe["ok"], probe.get("tpm")
                if probe["ok"]:
                    st.success(f"✅ {PROVIDERS[ss.provider]['label']} key verified: `{ss.model}` answered a test request.")
                    if ss.model_tpm and ss.model_tpm < 30000:
                        st.caption(f"Your plan allows {ss.model_tpm:,} tokens/minute on this model, so a run may "
                                   "pause briefly between steps. That's normal.")
                else:
                    st.error(f"`{ss.model}` failed its test: {probe['error']}")
                chain = backup_chain(ss.provider)
                if chain:
                    st.caption("🛟 Automatic backup if a step can't finish (no credit, limit, overload): "
                               + " → ".join(f"{PROVIDERS[p]['label']} · {m}" for p, m, _ in chain))
            if status["failed"]:
                with st.expander(f"Hidden models ({len(status['failed'])})"):
                    for m, p in status["failed"].items():
                        st.caption(f"**{m}**: {p['error']}")
            if st.button("↻ Re-check key & models", width="stretch"):
                _check.clear()
                _probe.clear()
                st.rerun()

        st.divider()
        st.subheader("📊 Usage")
        sess = ss.get("session_usage", [])
        c1, c2 = st.columns(2)
        c1.metric("Session tokens", f"{sum(e['prompt_tokens'] + e['completion_tokens'] for e in sess):,}")
        c2.metric("Session cost", f"${sum(e['cost_usd'] for e in sess):.4f}")
        try:
            rows = store.usage_rows()
            st.caption(f"All-time: {sum(r['prompt_tokens'] + r['completion_tokens'] for r in rows):,} tokens · "
                       f"${sum(r['cost_usd'] or 0 for r in rows):.4f}")
        except Exception as e:
            st.caption(f"Usage history unavailable: {e}")
