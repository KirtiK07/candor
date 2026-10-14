"""LLM wrapper over OpenAI-compatible APIs (Groq, Gemini, OpenAI): model listing, key checks, JSON calls,
usage capture, and automatic fallback to the next working provider when one can't finish a step."""
import json
import re

import openai
from openai import OpenAI

from core.config import setting
from core.tokens import cost, count_tokens

PROVIDERS = {
    "groq": {
        "label": "Groq",
        "env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "preferred": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"],
        # speech, moderation and tiny models that can't do this task. qwen on Groq caps output at
        # 1,000 tokens/minute, too little for a resume, and a single test call doesn't reliably reveal it.
        "exclude": ("whisper", "orpheus", "tts", "guard", "allam", "compound", "distil", "qwen"),
        # Groq checks expected output against per-minute limits, so cap it
        "max_output": 8000,
    },
    "gemini": {
        "label": "Gemini",
        "env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        # flash-lite first: fast, generous limits and reliably available; full Flash models are often overloaded
        "preferred": ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"],
        "exclude": ("tts", "image", "embedding", "transcribe", "audio", "robotics", "computer-use", "customtools",
                    "live", "nano-banana", "omni", "aqa"),
        "max_output": None,
    },
    "openai": {
        "label": "OpenAI",
        "env": "OPENAI_API_KEY",
        "base_url": None,
        "preferred": ["gpt-4.1-mini", "gpt-5-mini", "gpt-4o-mini", "gpt-4.1", "gpt-5", "gpt-4o",
                      "o4-mini", "o3", "gpt-4.1-nano", "gpt-5-nano"],
        "exclude": ("audio", "realtime", "tts", "transcribe", "whisper", "dall-e", "image", "embedding",
                    "moderation", "search", "instruct", "computer-use", "deep-research", "codex", "-pro",
                    "o1-mini", "o1-preview", "babbage", "davinci", "sora"),
        "max_output": None,
    },
}
DATED = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{4})$")


class LLMError(Exception):
    def __init__(self, msg: str, kind: str = "other"):
        super().__init__(msg)
        self.kind = kind  # "auth" | "quota" | "rate" | "too_large" | "unavailable" | "other"


# Errors where another provider may well succeed, so a run switches instead of failing.
SWITCH_KINDS = ("auth", "quota", "rate", "too_large", "unavailable")


def api_key(provider: str) -> str:
    return (setting(PROVIDERS[provider]["env"]) or "").strip()


def available_providers() -> list[str]:
    return [p for p in PROVIDERS if api_key(p)]


def default_provider() -> str | None:
    avail = available_providers()
    pref = str(setting("DEFAULT_PROVIDER", "") or "").lower()
    return pref if pref in avail else (avail[0] if avail else None)


def default_model(provider: str, models: list[str] | None = None) -> str:
    preferred = PROVIDERS[provider]["preferred"]
    if models:
        return next((m for m in preferred if m in models), models[0])
    return preferred[0]


def _body_message(e) -> str:
    body = getattr(e, "body", None)
    if not isinstance(body, dict):
        return ""
    if isinstance(body.get("error"), dict):
        body = body["error"]
    return body.get("message") or ""


def _friendly(e: Exception, label: str) -> LLMError:
    detail = _body_message(e) or str(e)
    if isinstance(e, openai.AuthenticationError):
        return LLMError(f"{label} rejected the API key: {detail}", "auth")
    if isinstance(e, (openai.RateLimitError, openai.APIStatusError)) and "request too large" in detail.lower():
        return LLMError(f"{label}: this model's per-minute token limit is too small for this request ({detail.split('. Need more')[0]}). "
                        "Pick another model or provider, or shorten the resume/JD.", "too_large")
    if isinstance(e, openai.RateLimitError):
        if "insufficient_quota" in str(e) or "credit" in detail.lower():
            return LLMError(f"Your {label} account has no remaining credit. ({detail})", "quota")
        return LLMError(f"{label} rate limit reached: {detail} Wait a minute and retry, or pick a smaller model.", "rate")
    if isinstance(e, openai.PermissionDeniedError):
        return LLMError(f"This {label} key isn't allowed to use that model. ({detail})", "auth")
    if isinstance(e, openai.NotFoundError):
        return LLMError(f"Model not found or not available on {label}. ({detail})")
    if isinstance(e, openai.InternalServerError) or "high demand" in detail.lower() or "overloaded" in detail.lower():
        return LLMError(f"{label} is temporarily overloaded: {detail}", "unavailable")
    if isinstance(e, openai.APITimeoutError):
        return LLMError(f"{label} took too long to respond (it may be overloaded).", "unavailable")
    if isinstance(e, openai.APIConnectionError):
        return LLMError(f"Could not reach {label}. Check your internet connection.")
    return LLMError(f"{label} error: {detail}")


def is_reasoning(model: str) -> bool:
    return bool(re.match(r"^(o\d|gpt-5)", model)) and "chat" not in model


def list_chat_models(provider: str, key: str, include_snapshots: bool = False) -> list[str]:
    """List chat-capable models the key can access (also validates the key)."""
    cfg = PROVIDERS[provider]
    try:
        data = list(OpenAI(api_key=key, base_url=cfg["base_url"], timeout=30).models.list())
    except openai.OpenAIError as e:
        raise _friendly(e, cfg["label"]) from e
    ids = [m.id.removeprefix("models/") for m in data if getattr(m, "active", True) is not False]
    ids = [m for m in ids if not any(x in m for x in cfg["exclude"])]
    if provider == "gemini":
        ids = [m for m in ids if m.startswith("gemini")]
    if provider == "openai":
        ids = [m for m in ids if m.startswith("gpt-") or re.match(r"^o\d", m)]
        if not include_snapshots:
            ids = [m for m in ids if not DATED.search(m)] or ids
    rank = {m: i for i, m in enumerate(cfg["preferred"])}
    return sorted(set(ids), key=lambda m: (rank.get(m, len(rank)), m))


PROBE_OUTPUT = 3000  # a resume rewrite needs ~2-3K output tokens; models that can't allow this are unusable here


def probe_model(provider: str, key: str, model: str) -> dict:
    """Make one tiny real request to prove the key can use this model, and read its token limit.

    Returns {"ok": True, "tpm": int|None} or {"ok": False, "kind": ..., "error": str}.
    """
    cfg = PROVIDERS[provider]
    client = OpenAI(api_key=key, base_url=cfg["base_url"], max_retries=0, timeout=20)
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=model, messages=[{"role": "user", "content": "Reply with the single word: ok"}],
            max_completion_tokens=PROBE_OUTPUT)
        raw.parse()
    except openai.OpenAIError as e:
        err = _friendly(e, cfg["label"])
        if err.kind == "rate" and "output tokens per minute" in str(err).lower():
            err.kind = "too_large"
        return {"ok": False, "kind": err.kind, "error": str(err)}
    tpm = raw.headers.get("x-ratelimit-limit-tokens")
    return {"ok": True, "tpm": int(tpm) if tpm and tpm.isdigit() else None}


def check_provider(provider: str, max_probes: int = 5) -> dict:
    """Validate the provider's key with real test calls and pick the best usable model.

    Probes models in preference order. For providers with many models (OpenAI) it stops at the first
    working one; other models are verified when the user selects them.
    """
    key = api_key(provider)
    models = list_chat_models(provider, key)  # raises LLMError on a bad key
    probes: dict[str, dict] = {}
    for m in models[:max_probes]:
        probes[m] = probe_model(provider, key, m)
        if not probes[m]["ok"] and probes[m]["kind"] in ("auth", "quota"):
            break  # key-level problem: every model will fail the same way
        if probes[m]["ok"] and len(models) > max_probes:
            break
    usable = [m for m in models if probes.get(m, {}).get("ok")]
    # A temporarily overloaded model stays selectable; models that can't do the job are hidden.
    failed = {m: p for m, p in probes.items() if not p["ok"] and p["kind"] != "unavailable"}
    key_error = next((p["error"] for p in failed.values() if p["kind"] in ("auth", "quota")), None)
    return {
        "models": [m for m in models if m not in failed],
        "probes": probes,
        "default": usable[0] if usable else None,
        "failed": failed,
        "key_error": key_error or (None if usable else "No model could complete a test request."),
    }


def _parse_json(content: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()  # reasoning models may emit this
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise ValueError("response was not JSON")


class LLM:
    def __init__(self, provider: str, model: str, fallbacks: list[tuple[str, str, int | None]] | None = None,
                 tpm: int | None = None):
        self.usage: list[dict] = []
        self.notices: list[str] = []
        self.fallbacks = list(fallbacks or [])  # (provider, model, tpm) to try in order if a step can't finish
        self._use(provider, model, tpm)

    def _use(self, provider: str, model: str, tpm: int | None = None) -> None:
        self.provider, self.model = provider, model
        self.tpm = tpm  # tokens-per-minute limit of the model, if known (Groq free tier: 8,000)
        self.cfg = PROVIDERS[provider]
        self.client = OpenAI(api_key=api_key(provider), base_url=self.cfg["base_url"], max_retries=5, timeout=240)

    def _record(self, step: str, resp) -> None:
        u = resp.usage
        pt, ct = (u.prompt_tokens, u.completion_tokens) if u else (0, 0)
        self.usage.append({
            "step": step, "model": self.model, "prompt_tokens": pt,
            "completion_tokens": ct, "cost_usd": cost(self.model, pt, ct) or 0.0,
        })

    def json_call(self, step: str, system: str, user: str) -> dict:
        while True:
            try:
                return self._json_call(step, system, user)
            except LLMError as e:
                if e.kind not in SWITCH_KINDS or not self.fallbacks:
                    raise
                provider, model, tpm = self.fallbacks.pop(0)
                self.notices.append(f"{self.cfg['label']} · {self.model} couldn't finish '{step}' ({e}). "
                                    f"Switched to {PROVIDERS[provider]['label']} · {model}.")
                self._use(provider, model, tpm)

    def _json_call(self, step: str, system: str, user: str) -> dict:
        needed = count_tokens(system + user, self.model)
        if self.tpm and needed > self.tpm * 0.95:
            raise LLMError(f"The '{step}' step needs ~{needed:,} input tokens, but {self.model} allows only "
                           f"{self.tpm:,} tokens per minute on your {self.cfg['label']} plan. Shorten the resume or JD "
                           f"(remove boilerplate), or switch provider.", "too_large")
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        if not is_reasoning(self.model):
            kwargs["temperature"] = 0.3
        if self.cfg["max_output"]:
            kwargs["max_completion_tokens"] = self.cfg["max_output"]
        last_err, json_retried = None, False
        for _ in range(5):
            try:
                resp = self.client.chat.completions.create(**kwargs)
            except openai.BadRequestError as e:
                # Some models reject temperature or JSON mode; drop the param and try again.
                msg = str(e)
                if "json_validate_failed" in msg:  # Groq: model produced invalid JSON in JSON mode
                    if json_retried:
                        kwargs.pop("response_format", None)
                    json_retried = True
                    continue
                if "temperature" in msg and "temperature" in kwargs:
                    kwargs.pop("temperature")
                    continue
                if "response_format" in msg and "response_format" in kwargs:
                    kwargs.pop("response_format")
                    continue
                raise _friendly(e, self.cfg["label"]) from e
            except openai.OpenAIError as e:
                raise _friendly(e, self.cfg["label"]) from e
            self._record(step, resp)
            choice = resp.choices[0]
            try:
                return _parse_json(choice.message.content or "")
            except ValueError as e:
                last_err = e
                if choice.finish_reason == "length":
                    raise LLMError(f"The model ran out of output tokens during '{step}'. Try another model.")
        raise LLMError(f"The model returned invalid JSON during '{step}' ({last_err}). Try again or switch models.")
