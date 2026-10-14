"""Item-level tailoring.

The model never returns a whole resume. It gets every bullet with a stable id (E1.2, P2.1, ED1.1, A3) and returns a
plan: rewrite / keep / remove per item, plus a new headline, summary, skills and ordering, each with a reason.
apply_plan() then builds the tailored resume from the ORIGINAL, so companies, titles, dates, degrees and project
names cannot change, whole roles/projects cannot disappear, and every change carries an explanation.
"""
import copy
import re

from core.ats_scorer import tokens
from core.renderer import resume_to_text

WORDS_PER_PAGE = 600
# (id prefix, resume key, bullet key)
ENTRY_SPECS = [("E", "experience", "bullets"), ("P", "projects", "bullets"), ("ED", "education", "details")]
BULLET_KEY = {key: bkey for _, key, bkey in ENTRY_SPECS}
SECTIONS = ["summary", "skills", "experience", "projects", "education", "certifications", "achievements",
            "additional_sections"]


def _s(v) -> str:
    return str(v).strip() if v else ""


def _norm(s) -> str:
    # "AWS EC2", "AWS (EC2)" and "aws-ec2" are the same skill
    return re.sub(r"[^a-z0-9+#]", "", _s(s).lower())


def entry_label(key: str, e: dict) -> str:
    if key == "experience":
        return f"Experience · {_s(e.get('title'))} @ {_s(e.get('company'))}"
    if key == "projects":
        return f"Project · {_s(e.get('name'))}"
    return f"Education · {_s(e.get('degree')) or _s(e.get('institution'))}"


def itemize(r: dict) -> tuple[str, dict[str, tuple[str, str]]]:
    """Resume as id-labelled text for the model, plus {item_id: (section label, original text)}."""
    lines = [f"HEADLINE: {_s(r.get('headline')) or '(none)'}", f"SUMMARY: {_s(r.get('summary')) or '(none)'}"]
    groups = ["{}: {}".format(_s(g.get("category")) or "Skills", ", ".join(_s(i) for i in g.get("items") or []))
              for g in r.get("skills") or []]
    lines.append("SKILLS: " + (" | ".join(groups) or "(none)"))
    items: dict[str, tuple[str, str]] = {}
    for prefix, key, bkey in ENTRY_SPECS:
        for i, e in enumerate(r.get(key) or [], 1):
            eid = f"{prefix}{i}"
            if key == "experience":
                head = f"{_s(e.get('title'))} at {_s(e.get('company'))} ({_s(e.get('start'))} – {_s(e.get('end'))})"
            elif key == "projects":
                tech = ", ".join(_s(t) for t in e.get("tech") or [] if _s(t))
                head = f"Project: {_s(e.get('name'))}" + (f" [tech: {tech}]" if tech else "")
            else:
                head = f"{_s(e.get('degree'))} {_s(e.get('field'))}, {_s(e.get('institution'))}".strip(" ,")
            lines.append(f"\n{eid}: {head}")
            for j, b in enumerate(e.get(bkey) or [], 1):
                if _s(b):
                    items[f"{eid}.{j}"] = (entry_label(key, e), _s(b))
                    lines.append(f"  {eid}.{j}: {_s(b)}")
    ach = [a for a in r.get("achievements") or [] if _s(a)]
    if ach:
        lines.append("\nACHIEVEMENTS")
        for i, a in enumerate(ach, 1):
            items[f"A{i}"] = ("Achievements", _s(a))
            lines.append(f"  A{i}: {_s(a)}")
    return "\n".join(lines), items


def _mostly_in(term: str, resume_tokens: set[str]) -> bool:
    """A multi-word JD phrase whose words are at least two-thirds in the resume already ('full-stack development')."""
    t = tokens(term)
    return len(t) > 1 and len(t & resume_tokens) * 3 >= len(t) * 2


def keyword_targets(ats_before: dict, forbidden: list[str], evidence: list[dict] | None = None,
                    resume_text: str = "") -> list[str]:
    """JD terms missing from the resume's wording that the candidate genuinely has.

    With keyword evidence from the JD analysis, terms marked present/implied qualify (with their evidence, so the
    model knows where they belong); absent ones never do. Terms the analysis didn't classify qualify only as phrases
    mostly made of words the resume already uses. Older analyses without evidence fall back to "anything not known
    to be missing".
    """
    missing = list(dict.fromkeys((ats_before.get("missing") or []) + (ats_before.get("alternatives") or [])))
    bad = tokens(" ".join(forbidden))
    if evidence:
        status = {_s(e.get("term")).lower(): (_s(e.get("status")).lower(), _s(e.get("evidence")))
                  for e in evidence if isinstance(e, dict)}
        resume_tokens = tokens(resume_text)
        out = []
        for t in missing:
            st, ev = status.get(t.lower(), ("", ""))
            if st in ("present", "implied"):
                out.append(f"{t} (evidence: {ev})" if ev else t)
            elif not st and t not in forbidden and _mostly_in(t, resume_tokens):
                out.append(f"{t} (only where it accurately describes the work)")
        return out
    return [t for t in missing if not (tokens(t) and tokens(t) <= bad)]


def min_rewrites(intensity: str, n_items: int, share: dict) -> int:
    return min(n_items, max(1, round(n_items * share.get(intensity, 0.7)))) if n_items else 0


def _word_count(r: dict) -> int:
    return len(resume_to_text(r).split())


def apply_plan(original: dict, plan: dict, page_limit: int) -> tuple[dict, list[dict]]:
    """Build the tailored resume from the original + the model's plan. Returns (resume, changes)."""
    new = copy.deepcopy(original)
    _, items = itemize(original)
    changes: list[dict] = []

    def change(kind, section, before="", after="", reason="", keywords=None, cid=""):
        changes.append({"type": kind, "section": section, "before": before, "after": after, "id": cid,
                        "reason": _s(reason), "jd_requirement": ", ".join(_s(k) for k in keywords or [] if _s(k))})

    # headline / summary
    for field, label in (("headline", "Headline"), ("summary", "Summary")):
        p = plan.get(field) or {}
        text = _s(p.get("text")) if isinstance(p, dict) else _s(p)
        if text and text != _s(original.get(field)):
            new[field] = text
            change("rewrite", label, _s(original.get(field)), text, p.get("reason") if isinstance(p, dict) else "",
                   p.get("keywords") if isinstance(p, dict) else None, field.upper())

    # skills
    sk = plan.get("skills") or {}
    groups = [{"category": _s(g.get("category")), "items": [_s(i) for i in g.get("items") or [] if _s(i)]}
              for g in (sk.get("groups") or []) if isinstance(g, dict)]
    groups = [g for g in groups if g["items"]]
    if groups:
        old_items = [_s(i) for g in original.get("skills") or [] for i in g.get("items") or [] if _s(i)]
        new_items = [i for g in groups for i in g["items"]]
        old_n, new_n = {_norm(i) for i in old_items}, {_norm(i) for i in new_items}
        new["skills"] = groups
        dropped = [i for i in old_items if _norm(i) not in new_n]
        added = [i for i in new_items if _norm(i) not in old_n]
        if added:
            change("rewrite", "Skills", "", ", ".join(added),
                   sk.get("reason") or "Added the JD's wording for skills you demonstrate.", cid="SKILLS")
        if dropped:
            change("remove", "Skills", ", ".join(dropped), "", sk.get("reason") or "Less relevant to this JD.")
        if not added and not dropped and old_items != new_items:
            change("reorder", "Skills", "", "", sk.get("reason") or "Most JD-relevant skills moved first.")

    # bullets / details / achievements
    plan_items, plan_order = {}, []
    for it in plan.get("items") or []:
        iid = _s(it.get("id")).upper() if isinstance(it, dict) else ""
        if iid in items and iid not in plan_items:
            plan_items[iid] = it
            plan_order.append(iid)
    removed: list[tuple[str, str, int | None, str, str]] = []  # (iid, key, entry index, text, reason)

    def build(ids: list[str], key: str, idx: int | None) -> list[str]:
        ordered = [i for i in plan_order if i in ids] + [i for i in ids if i not in plan_items]
        out = []
        for iid in ordered:
            label, orig = items[iid]
            it = plan_items.get(iid, {})
            action = _s(it.get("action")).lower() or "keep"
            if action == "remove":
                removed.append((iid, key, idx, orig, _s(it.get("reason"))))
                continue
            text = _s(it.get("text")) if action == "rewrite" and _s(it.get("text")) else orig
            if _norm(text) == _norm(orig):  # only punctuation/case differs: not a real rewrite
                text = orig
            out.append(text)
            if text != orig:
                change("rewrite", label, orig, text, it.get("reason"), it.get("keywords"), iid)
        kept_ids = [i for i in ordered if i not in {r[0] for r in removed}]
        if kept_ids != [i for i in ids if i in kept_ids] and len(kept_ids) > 1:
            change("reorder", items[ids[0]][0], "", "", "Bullets reordered so the most JD-relevant work comes first.")
        return out

    for prefix, key, bkey in ENTRY_SPECS:
        for i, e in enumerate(new.get(key) or []):
            eid = f"{prefix}{i + 1}"
            ids = [f"{eid}.{j}" for j in range(1, len(original[key][i].get(bkey) or []) + 1) if f"{eid}.{j}" in items]
            if ids:
                e[bkey] = build(ids, key, i)
    a_ids = [i for i in items if re.fullmatch(r"A\d+", i)]
    if a_ids:
        new["achievements"] = build(a_ids, "achievements", None)

    # project order (experience stays reverse-chronological)
    po = plan.get("project_order") or {}
    order = [_s(x).upper() for x in (po.get("order") or [])] if isinstance(po, dict) else []
    n_proj = len(new.get("projects") or [])
    if sorted(order) == [f"P{i}" for i in range(1, n_proj + 1)] and order != sorted(order, key=lambda x: int(x[1:])):
        new["projects"] = [new["projects"][int(x[1:]) - 1] for x in order]
        change("reorder", "Projects", "", "", po.get("reason") or "Most relevant projects moved first.")

    # section order
    so = plan.get("section_order") or {}
    sec = [x for x in (so.get("order") or []) if x in SECTIONS] if isinstance(so, dict) else []
    if sec:
        sec = list(dict.fromkeys(sec + [x for x in SECTIONS if x not in sec]))
        # only sections with content count: moving an empty section is not a visible change
        old = list(dict.fromkeys([x for x in original.get("section_order") or [] if x in SECTIONS and original.get(x)]))
        if [x for x in sec if x in old] != old:
            change("reorder", "Section order", "", " → ".join(x for x in sec if x in old),
                   so.get("reason") or "Most relevant sections first.")
        new["section_order"] = sec

    # Over-trimming guard: put removed items back while the resume still fits the page budget.
    budget = WORDS_PER_PAGE * max(1, int(page_limit or 1))
    for iid, key, idx, text, reason in removed:
        target = new["achievements"] if key == "achievements" else new[key][idx][BULLET_KEY[key]]
        if _word_count(new) + len(text.split()) <= budget:
            target.append(text)
            change("kept", items[iid][0], text, text,
                   f"The AI suggested removing this ({reason or 'no reason given'}), but your resume fits within "
                   f"{page_limit} page(s), so it was kept.")
        else:
            change("remove", items[iid][0], text, "", reason or "Removed to fit the page limit.")
    return new, changes


def change_report(changes: list[dict], stats: dict | None = None) -> str:
    """Plain-text 'what changed and why' report (also used for the downloadable file)."""
    out = ["WHAT WAS CHANGED AND WHY", ""]
    if stats:
        out += [f"Rewrote {stats.get('rewritten', 0)} of {stats.get('items', 0)} bullet points; "
                f"removed {stats.get('removed', 0)}; kept {stats.get('kept_unchanged', 0)} unchanged.", ""]
    titles = {"rewrite": "REWRITTEN", "reorder": "REORDERED", "remove": "REMOVED", "kept": "KEPT (not removed)"}
    for kind in ("rewrite", "reorder", "remove", "kept"):
        group = [c for c in changes if (c.get("type") or "rewrite") == kind]
        if not group:
            continue
        out.append(titles[kind])
        for c in group:
            out.append(f"- [{c.get('section')}]")
            if kind == "rewrite" and c.get("before"):
                out.append(f"    Before: {c['before']}")
            if c.get("after") and kind in ("rewrite", "reorder"):
                out.append(f"    {'After' if kind == 'rewrite' else 'New order'}: {c['after']}")
            if kind in ("remove", "kept"):
                out.append(f"    Item: {c.get('before')}")
            if c.get("reason"):
                out.append(f"    Why: {c['reason']}")
            if c.get("jd_requirement"):
                out.append(f"    JD keywords: {c['jd_requirement']}")
        out.append("")
    return "\n".join(out).strip()


def plan_stats(changes: list[dict], n_items: int) -> dict:
    bullet = [c for c in changes if c.get("section", "").split(" · ")[0] in ("Experience", "Project", "Education")
              or c.get("section") == "Achievements"]
    rewritten = sum(1 for c in bullet if c.get("type") == "rewrite")
    removed = sum(1 for c in bullet if c.get("type") == "remove")
    return {"items": n_items, "rewritten": rewritten, "removed": removed,
            "kept_unchanged": max(0, n_items - rewritten - removed)}
