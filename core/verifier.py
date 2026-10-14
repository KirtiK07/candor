"""Rule-based fact check: catches changed facts without trusting the LLM."""
import json
import re

from core.ats_scorer import term_in, tokens
from core.renderer import resume_to_text

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(text or "")}


def _source(original: dict, original_text: str, extra_facts: str) -> str:
    return " ".join([original_text or "", extra_facts or "", json.dumps(original, ensure_ascii=False)])


def check_claims(text: str, source: str, forbidden: list[str], where: str, forbidden_severity: str = "high") -> list[dict]:
    """Checks that apply to any generated text: invented numbers and requirements the candidate lacks."""
    issues = []
    for n in sorted(_numbers(text) - _numbers(source)):
        issues.append({"source": "rule", "severity": "medium",
                       "detail": f"{where}: the number '{n}' is not in your original resume. Check it isn't an invented metric."})
    text_tokens, src_tokens = tokens(text), tokens(source)
    for req in forbidden or []:
        if term_in(req, text_tokens) and not term_in(req, src_tokens):
            issues.append({"source": "rule", "severity": forbidden_severity,
                           "detail": f"{where}: mentions '{req}', which the JD asks for but your original resume "
                                     f"doesn't show. Make sure it isn't presented as experience you have."})
    return issues


def check_facts(original: dict, original_text: str, extra_facts: str, new: dict,
                forbidden: list[str] | None = None) -> list[dict]:
    source = _source(original, original_text, extra_facts)
    src_norm, src_tokens = _norm(source), tokens(source)
    issues = []

    def add(sev, detail):
        issues.append({"source": "rule", "severity": sev, "detail": detail})

    orig_exp = {(_norm(e.get("company")), _norm(e.get("title"))): e for e in original.get("experience") or []}
    new_exp_keys = set()
    for e in new.get("experience") or []:
        k = (_norm(e.get("company")), _norm(e.get("title")))
        new_exp_keys.add(k)
        if k[0] and k[0] not in src_norm:
            add("high", f"Company '{e.get('company')}' does not appear in the original resume.")
        if k[1] and k[1] not in src_norm:
            add("high", f"Job title '{e.get('title')}' does not appear in the original resume.")
        o = orig_exp.get(k)
        if o:
            n_new, n_old = len(e.get("bullets") or []), len(o.get("bullets") or [])
            if n_new > n_old:
                add("medium", f"'{e.get('title')}' at '{e.get('company')}' has {n_new} bullets but your original had "
                              f"{n_old}. Check the extra one isn't an invented achievement.")
            for f in ("start", "end"):
                if _norm(o.get(f)) != _norm(e.get(f)):
                    add("high", f"{f.title()} date for '{e.get('title')}' at '{e.get('company')}' changed "
                                f"from '{o.get(f)}' to '{e.get(f)}'.")
    for k, o in orig_exp.items():
        if k not in new_exp_keys:
            add("low", f"Role '{o.get('title')}' at '{o.get('company')}' was removed. Make sure that's intended.")

    for ed in new.get("education") or []:
        for f in ("institution", "degree"):
            if _norm(ed.get(f)) and _norm(ed.get(f)) not in src_norm:
                add("high", f"Education {f} '{ed.get(f)}' does not appear in the original resume.")

    for c in new.get("certifications") or []:
        if _norm(c.get("name")) and _norm(c.get("name")) not in src_norm:
            add("high", f"Certification '{c.get('name')}' does not appear in the original resume.")

    issues += check_claims(resume_to_text(new), source, forbidden or [], "Resume")

    for group in new.get("skills") or []:
        for item in group.get("items") or []:
            if _norm(item) and _norm(item) not in src_norm and not term_in(str(item), src_tokens):
                add("low", f"Skill '{item}' isn't written in the original resume. Keep it only if you genuinely have it.")
    return issues


_OUTCOME_TAIL = re.compile(r",\s*(improving|ensuring|enhancing|delivering|driving|enabling|boosting|increasing|"
                           r"streamlining|maintaining|resulting in|leading to)\b[^.;]*", re.I)


def check_added_outcomes(changes: list[dict]) -> list[dict]:
    """Flag rewritten bullets that gained a result clause ('…, improving X') the original never stated."""
    issues = []
    for c in changes:
        if (c.get("type") or "rewrite") != "rewrite" or not c.get("before"):
            continue
        m = _OUTCOME_TAIL.search(c.get("after") or "")
        if m and m.group(1).lower() not in (c["before"] or "").lower():
            issues.append({"source": "rule", "severity": "medium", "id": c.get("id", ""),
                           "claim": m.group(0).strip(", "),
                           "detail": f"{c.get('section')}: “{m.group(0).strip(', ')}” is a result your original bullet "
                                     f"doesn't state. Remove it unless it's true."})
    return issues


def check_cover_letter(original: dict, original_text: str, extra_facts: str, letter: str,
                       forbidden: list[str] | None = None) -> list[dict]:
    # A letter may honestly say "I haven't used X yet", so these mentions are only flagged for review.
    return check_claims(letter, _source(original, original_text, extra_facts), forbidden or [], "Cover letter", "low")


# Words a rewrite can swap mechanically, keeping the meaning.
_SWAPS = {"utilizing": "using", "utilized": "used", "utilizes": "uses", "utilize": "use", "leveraging": "using",
          "leveraged": "used", "leverages": "uses", "leverage": "use"}
_SWAP_RE = re.compile(r"\b(" + "|".join(_SWAPS) + r")\b", re.I)
# Filler and unearned claims: a recruiter reads past them, and they often overstate. Allowed when the original has them.
FILLER = ["robust", "seamless", "seamlessly", "cutting-edge", "state-of-the-art", "synergy", "passionate", "dynamic",
          "results-driven", "innovative", "proven", "track record", "demonstrated capability", "demonstrated ability",
          "expertise", "extensive", "scalable", "world-class", "best-in-class", "production-grade", "production-ready",
          "strong foundation", "strong foundations", "deep understanding", "highly skilled", "detail-oriented",
          "team player", "go-getter", "spearheaded", "various"]
_FILLER_RE = re.compile(r"\b(" + "|".join(re.escape(f) for f in sorted(FILLER, key=len, reverse=True)) + r")\b", re.I)


def swap_filler(text: str) -> str:
    """'utilizing X' -> 'using X' and similar, preserving a capital first letter."""
    def repl(m):
        new = _SWAPS[m.group(1).lower()]
        return new.capitalize() if m.group(1)[0].isupper() else new
    return _SWAP_RE.sub(repl, text or "")


def check_filler(changes: list[dict], original_text: str) -> list[dict]:
    """Filler words a rewrite introduced (the original never uses them), so they can be repaired."""
    orig = (original_text or "").lower()
    issues = []
    for c in changes:
        if (c.get("type") or "rewrite") != "rewrite" or not c.get("id") or c["id"] == "SKILLS":
            continue
        words = list(dict.fromkeys(m.group(1).lower() for m in _FILLER_RE.finditer(c.get("after") or "")))
        words = [w for w in words if w not in orig]
        if words:
            quoted = ", ".join(f"“{w}”" for w in words)
            issues.append({"source": "rule", "severity": "low", "id": c["id"], "claim": ", ".join(words),
                           "detail": f"{c.get('section')}: {quoted} {'are' if len(words) > 1 else 'is'} filler or an "
                                     f"unearned claim your original resume doesn't make. Use a concrete fact or cut it."})
    return issues
