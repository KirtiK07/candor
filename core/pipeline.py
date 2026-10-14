"""The redraft pipeline: extract → analyze JD → rewrite → verify → repair → cover letter."""
import json
import re
from dataclasses import asdict, dataclass, fields

from core import prompts
from core.ats_scorer import score as ats_score
from core.ats_scorer import term_in, tokens
from core.renderer import bullet_lines, pdf_pages, resume_to_text
from core.tailor import (BULLET_KEY, WORDS_PER_PAGE, _norm, apply_plan, itemize, keyword_targets, min_rewrites,
                         plan_stats)
from core.tokens import truncate_tokens
from core.verifier import _numbers, check_added_outcomes, check_cover_letter, check_facts, check_filler, swap_filler

DECLARATION = "I hereby declare that the information furnished above is true to the best of my knowledge and belief."


@dataclass
class Settings:
    intensity: str = "Moderate"
    region: str = "US"
    page_limit: int = 1
    include_links: bool = True
    include_photo: bool = False
    include_declaration: bool = False
    extra_facts: str = ""
    special_instructions: str = ""
    cover_letter: bool = False
    cover_tone: str = "Professional"
    hiring_manager: str = ""

    @classmethod
    def from_dict(cls, d: dict | None) -> "Settings":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in names})

    def to_dict(self) -> dict:
        return asdict(self)


MAX_JD_TOKENS = 3500  # long JDs are mostly boilerplate; capping keeps requests under small per-minute limits


def _dump(o) -> str:
    # Compact JSON: noticeably fewer tokens than pretty-printed, which matters on low token limits.
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def _slim_analysis(a: dict) -> dict:
    """What the rewrite step needs from the JD analysis, without the long evidence text."""
    gap = a.get("gap_analysis") or {}
    return {
        **{k: a.get(k) for k in ("job_title", "company", "seniority", "candidate_profile", "must_have_skills",
                                 "nice_to_have_skills", "keywords", "responsibilities")},
        "matched": [g.get("requirement") for g in gap.get("matched") or []],
        "transferable": [{"requirement": g.get("requirement"), "honest_phrasing": g.get("honest_phrasing")}
                         for g in gap.get("transferable") or []],
    }


def _unwrap(v):
    """Undo PDF line wrapping the model may have copied: 'cross-\\nencoder' -> 'cross-encoder', newline -> space."""
    if isinstance(v, str):
        v = re.sub(r"(?<=\w)-[ \t]*\n\s*(?=\w)", "-", v)
        return re.sub(r"\s*\n\s*", " ", v).strip()
    if isinstance(v, list):
        return [_unwrap(x) for x in v]
    if isinstance(v, dict):
        return {k: _unwrap(x) for k, x in v.items()}
    return v


def extract_resume(llm, resume_text: str) -> dict:
    data = llm.json_call("extract_resume", prompts.EXTRACT_SYSTEM, f'Resume text:\n"""\n{resume_text}\n"""')
    return _unwrap(data.get("resume", data) if isinstance(data.get("resume"), dict) else data)


def analyze_jd(llm, jd_text: str, resume_text: str) -> dict:
    jd_text = truncate_tokens(jd_text, MAX_JD_TOKENS)
    user = f"## JOB DESCRIPTION\n{jd_text}\n\n## CANDIDATE RESUME\n{resume_text}"
    return llm.json_call("analyze_jd", prompts.ANALYZE_SYSTEM, user)


def _evidence(jd_analysis: dict, statuses: tuple[str, ...]) -> list[str]:
    return [str(e.get("term")) for e in jd_analysis.get("keyword_evidence") or []
            if isinstance(e, dict) and e.get("term") and str(e.get("status", "")).lower() in statuses]


def missing_requirements(jd_analysis: dict) -> list[str]:
    """What the candidate lacks: gap-analysis 'missing' plus every JD term with no evidence in the resume."""
    gap = jd_analysis.get("gap_analysis") or {}
    out = [str(g.get("requirement")) for g in gap.get("missing") or [] if g.get("requirement")]
    return list(dict.fromkeys(out + _evidence(jd_analysis, ("absent",))))


def _forbidden_block(jd_analysis: dict) -> str:
    missing = missing_requirements(jd_analysis)
    if not missing:
        return ""
    return ("## FORBIDDEN CLAIMS\nThe candidate does NOT have these. Do not claim, imply or mention experience with "
            "any of them anywhere (not in the summary, bullets, skills or letter):\n- " + "\n- ".join(missing))


def _guard_skills(plan: dict, source: str, jd_analysis: dict) -> list[str]:
    """Drop skills the model added that the resume doesn't show (edits the plan in place). Returns what was blocked."""
    sk = plan.get("skills")
    if not isinstance(sk, dict) or not isinstance(sk.get("groups"), list):
        return []
    src_norm, src_tokens = _norm(source), tokens(source)
    # token sets of skills the analysis found evidence for; "NoSQL" counts when "NoSQL databases" is evidenced
    evidenced = [tokens(t) for t in _evidence(jd_analysis, ("present", "implied")) if tokens(t)]

    def ok(t: str) -> bool:
        tt = tokens(t)
        return bool(_norm(t)) and (_norm(t) in src_norm or term_in(t, src_tokens)
                                   or any(tt and tt <= e for e in evidenced))

    blocked = []
    for g in sk["groups"]:
        if not isinstance(g, dict):
            continue
        keep = []
        for item in g.get("items") or []:
            text = str(item or "").strip()
            if not text or ok(text):
                keep += [text] if text else []
                continue
            # "NoSQL databases (MongoDB, Redis)": judge the head and each listed skill separately
            head = re.sub(r"\s*\(.*\)", "", text).strip()
            inner = [x.strip() for x in re.split(r"[,/]", " ".join(re.findall(r"\(([^)]*)\)", text))) if x.strip()]
            parts = [p for p in [head, *inner] if p and p != text]
            if parts and ok(head) and all(ok(x) for x in inner):
                keep.append(text)
                continue
            keep += [p for p in parts if ok(p)]
            blocked += [p for p in parts if not ok(p)] or [text]
        g["items"] = list(dict.fromkeys(keep))
    return blocked


def _rewrite_message(resume_json, jd_analysis, company, job_title, s: Settings, targets, previous, feedback) -> str:
    items_text, items = itemize(resume_json)
    k = min_rewrites(s.intensity, len(items), prompts.INTENSITY_SHARE)
    words = len(resume_to_text(resume_json).split())
    budget = WORDS_PER_PAGE * max(1, int(s.page_limit or 1))
    jd_reqs = "; ".join(jd_analysis.get("jd_special_requirements") or []) or "none"
    lines = [
        f"## TARGET ROLE\n{job_title or 'see JD analysis'} at {company or 'see JD analysis'}",
        f"## JD ANALYSIS\n{_dump(_slim_analysis(jd_analysis))}",
        "## KEYWORD TARGETS (JD terms the candidate has but doesn't word the JD's way; use them where the evidence is)\n"
        + ("\n".join(f"- {t}" for t in targets) if targets else "none"),
        _forbidden_block(jd_analysis),
        "## SETTINGS",
        f"- {prompts.INTENSITY_RULES.get(s.intensity, prompts.INTENSITY_RULES['Moderate']).format(k=k, n=len(items))}",
        f"- Format: {prompts.REGION_RULES.get(s.region, '')}",
        f"- Word budget: {budget} words ({s.page_limit} page(s)). The resume is currently ~{words} words"
        + (", so do NOT remove anything." if words <= budget else f", so trim ~{words - budget} words, preferring "
           "tighter wording over removal."),
        f"- JD application instructions to honour where possible: {jd_reqs}",
        f"- Candidate's extra facts (true; you may use them in the summary): {s.extra_facts.strip() or 'none'}",
        f"- Candidate's special instructions (follow them): {s.special_instructions.strip() or 'none'}",
        f"## RESUME ITEMS\n{items_text}",
    ]
    if previous:
        lines += [
            f"## PREVIOUS TAILORED DRAFT\n{resume_to_text(previous)}",
            "## USER FEEDBACK ON THAT DRAFT (address it specifically; item ids still refer to RESUME ITEMS above)\n"
            f"{feedback.strip() or 'Produce a noticeably stronger alternative version.'}",
        ]
    return "\n\n".join(x for x in lines if x)


def _postprocess(resume: dict, s: Settings) -> dict:
    """Apply settings deterministically instead of trusting the model to do it."""
    if not s.include_links:
        contact = resume.setdefault("contact", {})
        for k in ("linkedin", "github", "portfolio"):
            contact[k] = ""
    if s.include_declaration:
        extra = resume.setdefault("additional_sections", []) or []
        resume["additional_sections"] = extra
        if not any(str(x.get("title", "")).lower() == "declaration" for x in extra):
            extra.append({"title": "Declaration", "items": [DECLARATION]})
    return resume


def _verify_message(original_text: str, extra_facts: str, changes: list[dict]) -> str:
    lines = []
    for c in changes:
        if c.get("type") != "rewrite" or not c.get("id"):
            continue
        if c["id"] == "SKILLS":
            lines.append(f"[SKILLS] skills added: {c.get('after')}")
        else:
            lines.append(f"[{c['id']}] {c.get('section')}\n  BEFORE: {c.get('before') or '(none)'}\n  AFTER: {c.get('after')}")
    return (f"## ORIGINAL RESUME\n{original_text}\n\n## EXTRA FACTS FROM CANDIDATE\n{extra_facts or 'none'}"
            "\n\n## CHANGES\n" + "\n".join(lines))


def _bullet_lists(resume: dict):
    for key, bkey in BULLET_KEY.items():
        for e in resume.get(key) or []:
            yield e.setdefault(bkey, [])
    yield resume.setdefault("achievements", [])


def _set_text(resume: dict, c: dict, new: str) -> bool:
    """Replace the text a change produced (headline, summary or a bullet) with `new`, in the resume and the change."""
    cid = str(c.get("id", "")).upper()
    if cid in ("HEADLINE", "SUMMARY"):
        resume[cid.lower()] = new
    else:
        target = next((lst for lst in _bullet_lists(resume) if c["after"] in lst), None)
        if target is None:
            return False
        target[target.index(c["after"])] = new
    c["after"] = new
    if c.get("before") and _norm(new) == _norm(c["before"]):
        c["type"] = "reverted"  # back to the original wording: no longer counts as a change
    return True


def _repair(llm, resume: dict, changes: list[dict], issues: list[dict], original_text: str) -> tuple[list, list]:
    """Fix serious fact-check issues in place. Returns (issues still open, issues fixed automatically)."""
    by_id = {c["id"]: c for c in changes if c.get("type") == "rewrite" and c.get("id")}
    serious = [i for i in issues if str(i.get("severity", "")).lower() in ("high", "medium")
               and str(i.get("id", "")).upper() in by_id]
    if not serious:
        return issues, []
    fixed_ids: set[str] = set()

    # An unsupported skill is simply dropped.
    for i in [i for i in serious if str(i.get("id")).upper() == "SKILLS"]:
        claim = _norm(i.get("claim"))
        for g in resume.get("skills") or []:
            if any(_norm(x) == claim for x in g.get("items") or []):
                g["items"] = [x for x in g["items"] if _norm(x) != claim]
                fixed_ids.add(id(i))

    text_issues = [i for i in serious if str(i.get("id")).upper() != "SKILLS"]
    if text_issues:
        flagged = "\n".join(
            f"[{c['id']}]\n  ORIGINAL: {c.get('before') or '(none)'}\n  CURRENT: {c['after']}\n  PROBLEM: {i.get('problem')}"
            for i in text_issues for c in [by_id[str(i['id']).upper()]])
        fixes = llm.json_call("repair", prompts.REPAIR_SYSTEM,
                              f"## ORIGINAL RESUME\n{original_text}\n\n## FLAGGED ITEMS\n{flagged}").get("fixes") or []
        fix_text = {str(f.get("id", "")).upper(): str(f.get("text") or "").strip()
                    for f in fixes if isinstance(f, dict)}
        for i in text_issues:
            cid = str(i["id"]).upper()
            c, new = by_id[cid], fix_text.get(cid)
            if new and new != c["after"] and _set_text(resume, c, new):
                fixed_ids.add(id(i))
    fixed = [i for i in issues if id(i) in fixed_ids]
    return [i for i in issues if id(i) not in fixed_ids], fixed


def _fit_to_pages(llm, resume: dict, original: dict, changes: list[dict], s: Settings, progress) -> None:
    """If the PDF overflows the page limit even at its most compact size, shorten bullets (in place) where it
    actually saves space: a wrapped bullet with only a few words on its last line loses a whole line when those
    words go. A shortened bullet must save a line and keep every number, or the original wording stays."""
    limit, a4 = max(1, int(s.page_limit or 1)), s.region != "US"
    _, items = itemize(original)
    by_id = {c["id"]: c for c in changes if c.get("type") == "rewrite" and c.get("id") in items}
    for _ in range(3):  # small cuts, re-measured each time, so wording isn't squeezed more than needed
        if pdf_pages(resume, a4, limit) <= limit:
            return
        progress(f"📏 Tightening wording to fit {limit} page{'s' * (limit > 1)}…")
        current = {iid: (by_id[iid]["after"] if iid in by_id else orig) for iid, (_, orig) in items.items()}
        live = {t for lst in _bullet_lists(resume) for t in lst}
        wrapped = [(bullet_lines(current[i], a4)[1], i) for i in current
                   if current[i] in live and bullet_lines(current[i], a4)[0] > 1]
        picks = sorted(wrapped)[:8]  # cheapest lines to save first
        if not picks:
            return
        msg = "\n".join(f"[{i}] (cut at least {n + 1} words) {current[i]}" for n, i in picks)
        out = llm.json_call("condense", prompts.CONDENSE_SYSTEM, msg).get("items") or []
        for f in out:
            if not isinstance(f, dict):
                continue
            iid, new = str(f.get("id", "")).upper(), str(f.get("text") or "").strip()
            old = current.get(iid)
            if (not old or not new or not _numbers(old) <= _numbers(new)
                    or bullet_lines(new, a4)[0] >= bullet_lines(old, a4)[0]):
                continue
            target = next((lst for lst in _bullet_lists(resume) if old in lst), None)
            if target is None:
                continue
            target[target.index(old)] = new
            if iid in by_id:
                by_id[iid]["after"] = new
            else:
                label, orig = items[iid]
                by_id[iid] = {"type": "rewrite", "section": label, "before": orig, "after": new, "id": iid,
                              "reason": f"Shortened to fit your {limit}-page limit.", "jd_requirement": ""}
                changes.append(by_id[iid])


def generate_version(llm, *, original_text: str, resume_json: dict, jd_analysis: dict, company: str,
                     job_title: str, settings: Settings, previous: dict | None = None, feedback: str = "",
                     progress=lambda msg: None) -> dict:
    progress("✍️ Tailoring your resume to the JD…")
    forbidden = missing_requirements(jd_analysis)
    before = ats_score(resume_to_text(resume_json), jd_analysis)
    targets = keyword_targets(before, forbidden, jd_analysis.get("keyword_evidence"), resume_to_text(resume_json))
    plan = llm.json_call("rewrite", prompts.REWRITE_SYSTEM,
                         _rewrite_message(resume_json, jd_analysis, company, job_title, settings, targets,
                                          previous, feedback))
    source = " ".join([original_text or "", settings.extra_facts or "", json.dumps(resume_json, ensure_ascii=False)])
    blocked = _guard_skills(plan, source, jd_analysis)
    new_resume, changes = apply_plan(resume_json, plan, settings.page_limit)
    new_resume = _postprocess(new_resume, settings)
    for c in changes:  # "utilizing" -> "using" etc. needs no model call
        if c.get("type") == "rewrite" and c.get("id") not in (None, "", "SKILLS"):
            swapped = swap_filler(c["after"])
            if swapped != c["after"]:
                _set_text(new_resume, c, swapped)
    _fit_to_pages(llm, new_resume, resume_json, changes, settings, progress)

    progress("🔎 Fact-checking every change against your original resume…")
    llm_issues, auto_fixed = [], []
    if any(c.get("type") == "rewrite" and c.get("id") for c in changes):
        llm_issues = llm.json_call("verify", prompts.VERIFY_SYSTEM,
                                   _verify_message(original_text, settings.extra_facts, changes)).get("issues") or []
        llm_issues = [i for i in llm_issues if isinstance(i, dict)]
        # Invented result clauses the rule check spots are repaired too (it re-runs on the final text below).
        outcomes = [{"id": i["id"], "claim": i["claim"], "problem": i["detail"], "severity": "medium"}
                    for i in check_added_outcomes(changes) + check_filler(changes, original_text) if i.get("id")]
        if any(str(i.get("severity", "")).lower() in ("high", "medium") for i in llm_issues + outcomes):
            progress("🛠 Correcting the flagged claims…")
            remaining, auto_fixed = _repair(llm, new_resume, changes, llm_issues + outcomes, original_text)
            llm_issues = [i for i in remaining if i not in outcomes]
    changes = [c for c in changes if c.get("type") != "reverted"]
    if auto_fixed:  # a repair can restore longer original wording, so check the page limit again
        _fit_to_pages(llm, new_resume, resume_json, changes, settings, progress)
    auto_fixed += [{"claim": s, "problem": "Skill not shown in your resume, so it was left out.", "severity": "high"}
                   for s in blocked]
    rule_issues = check_facts(resume_json, original_text, settings.extra_facts, new_resume, forbidden)
    rule_issues += check_added_outcomes(changes) + check_filler(changes, original_text)
    new_text = resume_to_text(new_resume)
    stats = plan_stats(changes, len(itemize(resume_json)[1]))

    progress("📊 Scoring ATS keyword match…")
    after = ats_score(new_text, jd_analysis)

    cover = None
    if settings.cover_letter:
        progress("✉️ Writing the cover letter…")
        profile = jd_analysis.get("candidate_profile") or {}
        cl = llm.json_call(
            "cover_letter", prompts.COVER_SYSTEM,
            f"## ROLE\n{job_title} at {company}\n\n## TONE\n{settings.cover_tone}\n\n"
            f"## HIRING MANAGER\n{settings.hiring_manager or 'unknown'}\n\n"
            f"## JD ANALYSIS\n{_dump({k: jd_analysis.get(k) for k in ('must_have_skills', 'responsibilities', 'keywords', 'jd_special_requirements')})}"
            f"\n\n## CANDIDATE PROFILE\n{_dump(profile)}"
            f"\n\n## ORIGINAL RESUME (the ONLY source of facts)\n{original_text}"
            f"\n\n## TAILORED RESUME (use for wording and emphasis only)\n{new_text}"
            f"\n\n## EXTRA FACTS\n{settings.extra_facts or 'none'}"
            f"\n\n## SPECIAL INSTRUCTIONS\n{settings.special_instructions or 'none'}\n\n{_forbidden_block(jd_analysis)}",
        )
        cover = (cl.get("cover_letter") or "").strip() or None
        if cover:  # the sign-off belongs on its own lines
            cover = re.sub(r"(?<=[.!])\s+(Sincerely|Best regards|Kind regards|Regards),\s*", r"\n\n\1,\n", cover)
        if cover and not cover.lower().startswith("dear"):
            cover = f"Dear {settings.hiring_manager.strip() or 'Hiring Manager'},\n\n{cover}"
        if cover:
            rule_issues += check_cover_letter(resume_json, original_text, settings.extra_facts, cover, forbidden)
            if job_title and job_title.lower() not in cover.lower():
                rule_issues.append({"source": "rule", "severity": "medium", "detail": f"Cover letter: doesn't name "
                                    f"the role exactly as '{job_title}'. Check the role title it uses is correct."})

    return {
        "resume_json": new_resume,
        "change_log": changes,
        "notes": [_note_text(n) for n in plan.get("notes_for_candidate") or [] if _note_text(n)],
        "verification": {"rule_issues": rule_issues, "llm_issues": llm_issues, "auto_fixed": auto_fixed},
        "ats_before": before["score"],
        "ats_after": after["score"],
        "ats_detail": {"before": before, "after": after, "stats": stats},
        "cover_letter": cover,
        "intensity": settings.intensity,
        "feedback": feedback or "",
    }


def _note_text(n) -> str:
    # Some models return notes as {"text": ...} objects instead of strings.
    if isinstance(n, dict):
        n = n.get("text") or n.get("note") or next((v for v in n.values() if isinstance(v, str)), "")
    return str(n or "").strip()


def usage_totals(entries: list[dict]) -> dict:
    return {
        "prompt_tokens": sum(e["prompt_tokens"] for e in entries),
        "completion_tokens": sum(e["completion_tokens"] for e in entries),
        "cost_usd": sum(e["cost_usd"] for e in entries),
    }
