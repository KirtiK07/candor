"""Streamlit UI tests. The OpenAI client is replaced with a fake, so no API key is needed."""
import copy

import pytest
from streamlit.testing.v1 import AppTest

import core.llm_client
import ui.sidebar
from core.llm_client import LLMError
from core.renderer import to_docx
from tests.fixtures import JD_ANALYSIS, JD_TEXT, RESUME_JSON, RESUME_TEXT


class FakeLLM:
    def __init__(self, provider, model, fallbacks=None, tpm=None):
        self.model = model
        self.usage = []
        self.notices = []

    def json_call(self, step, system, user):
        self.usage.append({"step": step, "model": self.model, "prompt_tokens": 1000,
                           "completion_tokens": 400, "cost_usd": 0.001})
        return {
            "extract_resume": copy.deepcopy(RESUME_JSON),
            "analyze_jd": copy.deepcopy(JD_ANALYSIS),
            "rewrite": {"summary": {"text": "Backend engineer building RESTful APIs with Python, PostgreSQL and "
                                            "Docker on AWS.", "reason": "Mirror the JD title", "keywords": ["Python"]},
                        "items": [{"id": "E1.1", "action": "rewrite", "reason": "JD asks for RESTful APIs",
                                   "text": "Built RESTful APIs in Python (Flask) serving 2 million requests per day"},
                                  {"id": "E2.2", "action": "remove", "reason": "Not relevant"}],
                        "notes_for_candidate": ["Be ready to discuss Kubernetes"]},
            "verify": {"issues": []},
            "cover_letter": {"cover_letter": "Dear Hiring Manager,\n\nBody.\n\nPriya Sharma"},
        }[step]


def _fake_models(provider, key, snaps=False):
    if key == "bad":
        raise LLMError("OpenAI rejected this API key: Your API key has expired.")
    if provider == "groq":
        return ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
    return ["gpt-4.1-mini", "gpt-4o"]


def _fake_probe(provider, key, model):
    if key == "nocredit":
        return {"ok": False, "kind": "quota", "error": "Your OpenAI account has no remaining credit."}
    if model.startswith("qwen"):
        return {"ok": False, "kind": "too_large", "error": "output tokens per minute (OTPM): Limit 1000"}
    return {"ok": True, "tpm": 8000 if provider == "groq" else None}


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(core.llm_client, "list_chat_models", _fake_models)
    monkeypatch.setattr(core.llm_client, "probe_model", _fake_probe)
    monkeypatch.setattr(ui.sidebar, "probe_model", _fake_probe)
    monkeypatch.setattr(ui.sidebar, "LLM", FakeLLM)
    ui.sidebar._check.clear()
    ui.sidebar._probe.clear()

    def make(key, groq_key=None, login=None):
        for var in ("APP_USERNAME", "APP_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        if login:
            monkeypatch.setenv("APP_USERNAME", login[0])
            monkeypatch.setenv("APP_PASSWORD", login[1])
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("DEFAULT_PROVIDER", "openai")
        if key is None:
            monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        else:
            monkeypatch.setenv("OPENAI_API_KEY", key)
        if groq_key:
            monkeypatch.setenv("GROQ_API_KEY", groq_key)
        return AppTest.from_file("../app.py", default_timeout=60).run()
    return make


def _button(at, label):
    return next(b for b in at.button if label in b.label)


def test_missing_key_explains_env(make_app):
    at = make_app(None)
    assert not at.exception, at.exception
    assert any(".env" in e.value for e in at.sidebar.error)


def test_bad_key_shows_reason(make_app):
    at = make_app("bad")
    assert any("expired" in e.value for e in at.sidebar.error)


def test_generate_without_inputs_warns(make_app):
    at = make_app("sk-test")
    _button(at, "Generate Tailored Resume").click().run()
    assert any("Please add" in w.value for w in at.warning)


def test_full_flow_redraft_retry_history(make_app):
    at = make_app("sk-test")
    assert at.sidebar.selectbox(key="model").value == "gpt-4.1-mini"
    assert not at.sidebar.text_input  # no API key box in the UI any more
    at.text_area(key="in_resume_text").input(RESUME_TEXT)
    at.text_area(key="in_jd").input(JD_TEXT)
    at.checkbox(key="in_cover").check()
    at.checkbox(key="in_decl").check().run()

    _button(at, "Generate Tailored Resume").click().run()
    assert not at.exception, at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Backend Engineer @ FinNova Technologies" in md          # title/company auto-detected
    assert "Token usage for this version" in md
    assert "What was changed and why" in md
    assert "JD asks for RESTful APIs" in " ".join(c.value for c in at.caption)      # reason shown under the resume
    assert "Kept (the AI wanted to remove these" in md                              # E2.2 restored: fits on 1 page
    assert any(m.label == "Bullets rewritten" and m.value == "1 of 5" for m in at.metric)
    assert any(m.label == "Total tokens" and m.value == "7,000" for m in at.metric)  # 5 calls x 1,400

    retry = next(b for b in at.button if b.label == "🔁 Retry" and b.key.startswith("cur_"))
    at.text_area(key=retry.key.replace("_retry_", "_fb_")).input("More concise")
    retry.click().run()
    assert not at.exception, at.exception
    cur_radio = next(r for r in at.radio if r.key.startswith("cur_sel_"))
    assert len(cur_radio.options) == 2 and cur_radio.index == 1  # new version is auto-selected

    assert any("FinNova Technologies" in str(df.value.to_dict()) for df in at.dataframe)
    assert any(m.label == "API calls" and m.value == "8" for m in at.metric)


def test_jd_parsed_from_uploaded_file():
    """The JD uploader reuses extract_text; check a DOCX JD round-trips into text."""
    from core.parser import extract_text

    jd_doc = to_docx({"name": "FinNova Backend Engineer", "summary": JD_TEXT})
    assert "Kubernetes" in extract_text("jd.docx", jd_doc)


def test_provider_switch_lists_groq_models(make_app):
    at = make_app("sk-test", groq_key="gsk-test")
    assert at.sidebar.radio(key="provider").options == ["Groq", "OpenAI"]
    assert at.sidebar.selectbox(key="model").value == "gpt-4.1-mini"
    at.sidebar.radio(key="provider").set_value("groq").run()
    assert not at.exception, at.exception
    assert at.sidebar.selectbox(key="model").value == "openai/gpt-oss-120b"


def test_llm_falls_back_when_primary_out_of_credit(monkeypatch):
    import core.llm_client as lc

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    llm = lc.LLM("openai", "gpt-4.1-mini",
                 fallbacks=[("groq", "openai/gpt-oss-120b", 8000), ("gemini", "gemini-3.5-flash-lite", None)])
    calls = []

    def fake_call(step, system, user):
        calls.append(llm.provider)
        if llm.provider == "openai":
            raise LLMError("no credit", "quota")
        if llm.provider == "groq":
            raise LLMError("Request too large", "too_large")
        return {"ok": True}

    monkeypatch.setattr(llm, "_json_call", fake_call)
    assert llm.json_call("rewrite", "s", "u") == {"ok": True}
    assert calls == ["openai", "groq", "gemini"] and llm.model == "gemini-3.5-flash-lite"
    assert len(llm.notices) == 2 and llm.tpm is None

    llm2 = lc.LLM("groq", "openai/gpt-oss-120b")
    monkeypatch.setattr(llm2, "_json_call", lambda *a: (_ for _ in ()).throw(LLMError("bad json")))
    with pytest.raises(LLMError):  # non-switchable errors still surface
        llm2.json_call("rewrite", "s", "u")


def test_limited_model_hidden_and_best_model_preselected(make_app):
    at = make_app(None, groq_key="gsk-test")
    sel = at.sidebar.selectbox(key="model")
    assert sel.value == "openai/gpt-oss-120b"
    assert not any("qwen" in o for o in sel.options)                 # 1,000 token/min output cap: hidden
    assert any("key verified" in s.value for s in at.sidebar.success)


def test_starts_on_working_provider_when_default_has_no_credit(make_app):
    at = make_app("nocredit", groq_key="gsk-test")                   # DEFAULT_PROVIDER=openai in fixture
    assert at.sidebar.radio(key="provider").value == "groq"
    assert at.sidebar.selectbox(key="model").value == "openai/gpt-oss-120b"


def test_login_page_blocks_until_correct_id_and_password(make_app, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    at = make_app("sk-ok", login=("kirti", "s3cret-pass"))
    assert not at.tabs and at.text_input  # only the sign-in form is shown
    at.text_input[0].input("kirti")
    at.text_input[1].input("wrong")
    at.button[0].click().run()
    assert any("Wrong ID or password" in e.value for e in at.error) and not at.tabs
    at.text_input[1].input("s3cret-pass")
    at.button[0].click().run()
    assert at.tabs and not at.exception
    sign_out = next(b for b in at.sidebar.button if "Sign out" in b.label)
    sign_out.click().run()
    assert not at.tabs


def test_history_cards_show_original_jd_and_tailored_with_downloads(make_app):
    at = make_app("sk-test")
    at.text_area(key="in_resume_text").input(RESUME_TEXT)
    at.text_area(key="in_jd").input(JD_TEXT).run()
    _button(at, "Generate Tailored Resume").click().run()
    assert not at.exception, at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "📄 Original resume" in md and "📋 Job description" in md and "✨ Tailored resume" in md
    assert "History older than 30 days is deleted automatically" in " ".join(c.value for c in at.caption)
    labels = [b.label for b in at.get("download_button")]
    assert {"⬇️ Original (.txt)", "⬇️ Job description (.txt)", "⬇️ PDF", "⬇️ DOCX"} <= set(labels)

    at.text_input(key="hist_clear_confirm").input("DELETE").run()
    next(b for b in at.button if b.key == "hist_clear").click().run()
    assert not at.exception, at.exception
    assert any("No tailored resumes yet" in i.value for i in at.info)
