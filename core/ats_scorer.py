"""Local (no-LLM) ATS keyword match score."""
import re

_SYNONYM_GROUPS = [
    {"javascript", "js"}, {"typescript", "ts"}, {"kubernetes", "k8s"},
    {"machine learning", "ml"}, {"artificial intelligence", "ai"},
    {"amazon web services", "aws"}, {"google cloud platform", "google cloud", "gcp"},
    {"microsoft azure", "azure"}, {"ci/cd", "continuous integration", "cicd"},
    {"postgresql", "postgres"}, {"natural language processing", "nlp"},
    {"node.js", "nodejs", "node"}, {"react", "react.js", "reactjs"},
    {"user experience", "ux"}, {"user interface", "ui"},
    {"large language models", "large language model", "llm", "llms"},
    {"rest api", "rest apis", "restful", "restful services"},
    {"object oriented programming", "oop"}, {"power bi", "powerbi"},
]
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#]*(?:\.[a-z0-9]+)*")


def _stem(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 5 and t.endswith("ing"):
        t = t[:-3]
    elif len(t) > 4 and t.endswith("ed"):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    if len(t) > 4 and t.endswith("e"):
        t = t[:-1]
    return t


def tokens(text: str) -> set[str]:
    return {_stem(t) for t in _TOKEN.findall((text or "").lower())}


def _variants(term: str) -> set[str]:
    t = term.lower().strip()
    for group in _SYNONYM_GROUPS:
        if t in group:
            return group
    return {t}


def term_in(term: str, text_tokens: set[str]) -> bool:
    for v in _variants(term):
        vt = [_stem(t) for t in _TOKEN.findall(v)]
        if vt and all(t in text_tokens for t in vt):
            return True
    return False


def _clean(term) -> str:
    term = str(term or "").strip()
    return "" if "year" in term.lower() else term


def _units(jd_analysis: dict) -> list[tuple[list[str], int]]:
    """Scoring units as (alternative terms, weight).

    A JD requirement with alternatives ("React, Angular or TypeScript") is ONE unit, met by any option. Required
    units count double. Skills and keywords not covered by a requirement group are single-term units.
    """
    units: list[tuple[list[str], int]] = []
    seen: set[str] = set()
    for g in jd_analysis.get("requirement_groups") or []:
        if not isinstance(g, dict):
            continue
        options = list(dict.fromkeys(t for t in map(_clean, g.get("options") or []) if t))
        options = [t for t in options if t.lower() not in seen]
        if options:
            units.append((options, 2 if g.get("required") else 1))
            seen |= {t.lower() for t in options}
    for key, w in (("must_have_skills", 2), ("nice_to_have_skills", 1), ("keywords", 1)):
        for term in map(_clean, jd_analysis.get(key) or []):
            if term and term.lower() not in seen:
                units.append(([term], w))
                seen.add(term.lower())
    return units


def score(resume_text: str, jd_analysis: dict) -> dict:
    """Weighted share of JD requirements the resume shows; required ones count double.

    Returns matched terms, `missing` (requirements not met at all) and `alternatives` (options the resume lacks
    for requirements it already meets through another option, e.g. React when JavaScript covers "React or JS").
    """
    units = _units(jd_analysis)
    if not units:
        return {"score": 0, "matched": [], "missing": [], "alternatives": []}
    text_tokens = tokens(resume_text)
    matched, missing, alternatives, got = [], [], [], 0
    for options, w in units:
        hits = [t for t in options if term_in(t, text_tokens)]
        if hits:
            got += w
            matched += hits
            alternatives += [t for t in options if t not in hits]
        else:
            missing += options
    total = sum(w for _, w in units)
    return {"score": round(100 * got / total), "matched": matched, "missing": missing, "alternatives": alternatives}
