"""Shows one application's versions: preview, diff, change log, gaps, fact check, cover letter, retry."""
import json

import pandas as pd
import streamlit as st

from core.diffing import diff_html
from core.llm_client import LLMError
from core.pipeline import Settings, generate_version, usage_totals
from core.renderer import (cover_letter_to_docx, cover_letter_to_pdf, resume_to_markdown, resume_to_text,
                           to_docx, to_pdf)
from core.tailor import change_report
from ui.common import INTENSITIES, INTENSITY_HELP, model_label, record_usage, safe_filename
from ui.sidebar import make_llm

SEV_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}


@st.cache_data(show_spinner=False, max_entries=32)
def _resume_files(resume_json_str: str, photo: bytes | None, a4: bool, fit_pages: int):
    r = json.loads(resume_json_str)
    pdf, pages = to_pdf(r, photo, a4, fit_pages)
    return to_docx(r, photo, a4), pdf, pages


@st.cache_data(show_spinner=False, max_entries=32)
def _cover_files(text: str, a4: bool):
    return cover_letter_to_docx(text, a4), cover_letter_to_pdf(text, a4)


def _issues(v: dict) -> list[dict]:
    ver = v.get("verification") or {}
    out = [{"severity": i.get("severity", "low"), "text": i.get("detail", ""), "by": "Rule check"}
           for i in ver.get("rule_issues") or []]
    out += [{"severity": str(i.get("severity", "low")).lower(),
             "text": f"“{i.get('claim', '')}”: {i.get('problem', '')}", "by": "AI fact-checker"}
            for i in ver.get("llm_issues") or []]
    return out


def _auto_fixed(v: dict) -> list[str]:
    return [f"“{i.get('claim', '')}”: {i.get('problem', '')}"
            for i in (v.get("verification") or {}).get("auto_fixed") or []]


def render_results(store, app_id: int, key: str) -> None:
    ss = st.session_state
    app = store.get_application(app_id)
    if not app:
        st.warning("This application no longer exists.")
        return
    versions = store.get_versions(app_id)
    if not versions:
        st.info("No versions saved for this application.")
        return
    by_id = {v["id"]: v for v in versions}
    sel_key = f"{key}_sel_{app_id}"
    if f"{sel_key}_pending" in ss:
        ss[sel_key] = ss.pop(f"{sel_key}_pending")
    if ss.get(sel_key) not in by_id:
        ss[sel_key] = next((v["id"] for v in versions if v["is_final"]), versions[-1]["id"])

    st.markdown(f"### 🎯 {app['job_title']} @ {app['company']}")
    vid = st.radio("Version", list(by_id), key=sel_key, horizontal=True,
                   format_func=lambda i: f"v{by_id[i]['version_no']}" + (" ⭐ final" if by_id[i]["is_final"] else ""))
    v = by_id[vid]
    inputs = app.get("inputs") or {}
    issues = _issues(v)
    serious = [i for i in issues if i["severity"] in ("high", "medium")]

    m = st.columns(3)
    m[0].metric("ATS keyword match", f"{v['ats_after']}%", f"{v['ats_after'] - v['ats_before']:+d} pts vs original",
                help="Share of the job's requirements your resume shows. Alternatives ('React or JavaScript') "
                     "count once; required items count double. Only true skills can raise it.")
    m[1].metric("Fact check", "✅ Clean" if not serious else f"⚠️ {len(serious)} to review",
                help="Every change was compared with your original resume. Details in the Fact check tab.")
    m[2].metric("Original ATS match", f"{v['ats_before']}%", help="The same score for your resume before tailoring.")
    st.caption(f"Created {v['created_at']} · Intensity: {v['intensity']}"
               + (f" · Feedback: “{v['feedback'][:120]}”" if v.get("feedback") else ""))
    _render_token_usage(store, v)

    # ---- downloads
    photo = app.get("photo") if inputs.get("include_photo") else None
    a4 = inputs.get("region", "US") != "US"
    text = resume_to_text(v["resume_json"])
    base = safe_filename(v["resume_json"].get("name", ""), app["company"], app["job_title"], f"v{v['version_no']}")
    limit = int(inputs.get("page_limit", 1))
    try:
        docx_b, pdf_b, pages = _resume_files(json.dumps(v["resume_json"], sort_keys=True), photo, a4, limit)
    except Exception as e:
        st.error(f"Couldn't build the DOCX/PDF: {e}")
        docx_b = pdf_b = None
        pages = 0
    if pages > limit:
        st.warning(f"The PDF runs to {pages} pages but you asked for {limit}. "
                   f"Retry with feedback like “condense to {limit} page” or a stronger intensity.")
    if inputs.get("cover_letter") and not v.get("cover_letter"):
        why = next((i.get("detail") for i in (v.get("verification") or {}).get("rule_issues") or []
                    if i.get("id") == "COVER_LETTER"), "")
        st.warning(f"✉️ No cover letter in this version. {why or 'Use Retry below with the cover letter box ticked.'}")
    changes = v.get("change_log") or []
    stats = (v.get("ats_detail") or {}).get("stats")
    report = change_report(changes, stats)
    d = st.columns(5)
    if docx_b:
        d[0].download_button("⬇️ DOCX (best for ATS)", docx_b, f"{base}.docx", key=f"{key}_docx_{vid}",
                             help="Word file: the safest format for applicant tracking systems.",
                             mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             width="stretch")
        d[1].download_button("⬇️ PDF", pdf_b, f"{base}.pdf", "application/pdf", key=f"{key}_pdf_{vid}",
                             help="Polished PDF fitted to your page limit: best for emailing a person.",
                             width="stretch")
    d[2].download_button("⬇️ Plain text", text, f"{base}.txt", key=f"{key}_txt_{vid}", width="stretch",
                         help="For pasting into online application forms.")
    d[3].download_button("⬇️ Change report", report, f"{base}_changes.txt", key=f"{key}_rep_{vid}", width="stretch",
                         help="What was changed and why. For you, not for the employer.")
    if not v["is_final"] and d[4].button("⭐ Mark as final", key=f"{key}_final_{vid}", width="stretch",
                                         help="The version History and the ZIP export show for this application."):
        store.set_final(app_id, vid)
        st.rerun()

    # ---- detail tabs
    names = ["📄 Resume & why it changed", "🔍 Side-by-side diff", "🎯 Skill gaps", f"✅ Fact check ({len(issues)})"]
    if v.get("cover_letter"):
        names.append("✉️ Cover letter")
    tabs = st.tabs(names)
    with tabs[0]:
        with st.container(border=True):
            st.markdown(resume_to_markdown(v["resume_json"]))
        _render_changes(changes, stats, v.get("notes") or [])
    with tabs[1]:
        st.caption("Red = removed or reworded from your original, green = new wording.")
        with st.container(height=600):
            st.markdown(diff_html(resume_to_text(app["resume_json"]), text), unsafe_allow_html=True)
    with tabs[2]:
        _render_gaps(app, v)
    with tabs[3]:
        fixed = _auto_fixed(v)
        if not issues:
            st.success("No unsupported claims found. Everything traces back to your original resume.")
        if fixed:
            with st.expander(f"🛠 Caught and corrected automatically ({len(fixed)})"):
                st.caption("The AI drafted these, the fact check flagged them, and they were fixed or left out "
                           "before you saw the resume.")
                for t in fixed:
                    st.markdown(f"- {_md(t)}")
        for i in sorted(issues, key=lambda x: ["high", "medium", "low"].index(x["severity"])
                        if x["severity"] in ("high", "medium", "low") else 3):
            st.markdown(f"{SEV_ICON.get(i['severity'], '⚪')} **{i['severity'].title()}** · {i['text']}  \n"
                        f"<small>{i['by']}</small>", unsafe_allow_html=True)
    if v.get("cover_letter"):
        with tabs[4]:
            st.text_area("Cover letter", v["cover_letter"], height=420, key=f"{key}_cl_{vid}")
            cl_docx, cl_pdf = _cover_files(v["cover_letter"], a4)
            cbase = safe_filename(v["resume_json"].get("name", ""), app["company"], "cover_letter", f"v{v['version_no']}")
            c = st.columns(3)
            c[0].download_button("⬇️ DOCX", cl_docx, f"{cbase}.docx", key=f"{key}_cldocx_{vid}", width="stretch")
            c[1].download_button("⬇️ PDF", cl_pdf, f"{cbase}.pdf", "application/pdf", key=f"{key}_clpdf_{vid}", width="stretch")
            c[2].download_button("⬇️ Text", v["cover_letter"], f"{cbase}.txt", key=f"{key}_cltxt_{vid}", width="stretch")

    _render_retry(store, app, v, serious, key)


def _md(t) -> str:
    return str(t or "").replace("$", "\\$").replace("*", "\\*").replace("_", "\\_")


def _render_changes(changes: list[dict], stats: dict | None, notes: list[str]) -> None:
    """'What was changed and why', shown right under the resume."""
    st.markdown("### 📝 What was changed and why")
    if stats:
        c = st.columns(3)
        c[0].metric("Bullets rewritten", f"{stats['rewritten']} of {stats['items']}",
                    help="Bullets reworded for this job. The rest were already a good fit and kept.")
        c[1].metric("Bullets removed", stats["removed"])
        c[2].metric("Kept as written", stats["kept_unchanged"])
    if not changes:
        st.info("No changes were recorded for this version.")
    by_type = lambda t: [c for c in changes if (c.get("type") or "rewrite") == t]  # noqa: E731

    for c in by_type("rewrite"):
        with st.container(border=True):
            st.markdown(f"**✏️ {_md(c.get('section'))}**")
            if c.get("before"):
                st.markdown(f"<span style='color:#94A3B8'>Before:</span> {_md(c['before'])}", unsafe_allow_html=True)
            st.markdown(f"<span style='color:#34D399;font-weight:600'>After:</span> {_md(c.get('after'))}", unsafe_allow_html=True)
            why = _md(c.get("reason")) or "Tailored to the JD."
            st.caption(f"Why: {why}" + (f"  ·  JD keywords: {c['jd_requirement']}" if c.get("jd_requirement") else ""))
    moves = by_type("reorder")
    if moves:
        st.markdown("**↕️ Reordered**")
        for c in moves:
            st.markdown(f"- **{_md(c.get('section'))}**{(': ' + _md(c['after'])) if c.get('after') else ''}. "
                        f"_{_md(c.get('reason'))}_")
    removed = by_type("remove")
    if removed:
        st.markdown("**🗑️ Removed**")
        for c in removed:
            st.markdown(f"- **{_md(c.get('section'))}**: “{_md(c.get('before'))}”  \n  Why: {_md(c.get('reason'))}")
    kept = by_type("kept")
    if kept:
        st.markdown("**🛡️ Kept (the AI wanted to remove these, but they fit within your page limit)**")
        for c in kept:
            st.markdown(f"- **{_md(c.get('section'))}**: “{_md(c.get('before'))}”")
    if notes:
        st.markdown("**💡 Notes for you**")
        for n in notes:
            st.markdown(f"- {_md(n)}")


STEP_NAMES = {"extract_resume": "Read resume", "analyze_jd": "Analyze JD & gaps", "rewrite": "Tailor resume",
              "verify": "Fact check", "repair": "Fix flagged claims", "condense": "Fit to page limit",
              "cover_letter": "Cover letter"}


def _render_token_usage(store, v: dict) -> None:
    pt, ct = v["prompt_tokens"] or 0, v["completion_tokens"] or 0
    with st.container(border=True):
        st.markdown(f"**🧮 Token usage for this version** (model `{v['model']}`)")
        c = st.columns(4)
        c[0].metric("Input tokens", f"{pt:,}")
        c[1].metric("Output tokens", f"{ct:,}")
        c[2].metric("Total tokens", f"{pt + ct:,}")
        c[3].metric("Approx. cost", f"${v['cost_usd'] or 0:.4f}")
        try:
            steps = [r for r in store.usage_rows() if r.get("version_id") == v["id"]]
        except Exception:
            steps = []
        if steps:
            st.dataframe(pd.DataFrame([{
                "Step": STEP_NAMES.get(r["step"], r["step"]), "Input": r["prompt_tokens"],
                "Output": r["completion_tokens"], "Total": r["prompt_tokens"] + r["completion_tokens"],
                "Cost ($)": round(r["cost_usd"] or 0, 5),
            } for r in steps]), hide_index=True, width="stretch")


def _render_gaps(app: dict, v: dict) -> None:
    analysis = app.get("jd_analysis") or {}
    gap = analysis.get("gap_analysis") or {}
    c = st.columns(3)
    with c[0]:
        st.markdown("**✅ You match**")
        for g in gap.get("matched") or []:
            st.markdown(f"- **{g.get('requirement')}**: {g.get('evidence', '')}")
    with c[1]:
        st.markdown("**🔄 Transferable (reworded honestly)**")
        for g in gap.get("transferable") or []:
            st.markdown(f"- **{g.get('requirement')}**: {g.get('honest_phrasing') or g.get('evidence', '')}")
    with c[2]:
        st.markdown("**❌ Missing (not added to your resume)**")
        for g in gap.get("missing") or []:
            st.markdown(f"- **{g.get('requirement')}**: {g.get('advice', '')}")
    after = (v.get("ats_detail") or {}).get("after") or {}
    if after.get("missing"):
        st.markdown("**JD requirements your resume doesn't show:** " + ", ".join(f"`{k}`" for k in after["missing"]))
    if after.get("alternatives"):
        st.markdown("**Alternatives you don't list** (the requirement is already met by another option, so these "
                    "don't lower your score): " + ", ".join(f"`{k}`" for k in after["alternatives"]))
    if analysis.get("jd_special_requirements"):
        st.markdown("**📌 Application instructions found in the JD:**")
        for r in analysis["jd_special_requirements"]:
            st.markdown(f"- {r}")


def _render_retry(store, app: dict, v: dict, serious: list[dict], key: str) -> None:
    ss = st.session_state
    with st.expander("🔁 Not satisfied? Retry this version", expanded=False):
        if not ss.get("models"):
            st.info("Retry needs a working API key in `.env` (see the sidebar).")
            return
        st.caption(f"Builds a new version from v{v['version_no']} plus your feedback. Earlier versions are kept.")
        aid = app["id"]
        fb = st.text_area("What should change?", key=f"{key}_fb_{aid}",
                          placeholder="e.g. More concise, emphasize my Python and AWS work, keep it to 1 page, "
                                      "make the summary less generic…")
        c = st.columns(3)
        models = ss.models
        default = models.index(ss.model) if ss.get("model") in models else 0
        model = c[0].selectbox("Model", models, index=default, key=f"{key}_rm_{aid}", format_func=model_label)
        intensity = c[1].select_slider("Intensity", INTENSITIES, value=v["intensity"] or "Moderate",
                                       key=f"{key}_ri_{aid}", help=INTENSITY_HELP)
        cover = c[2].checkbox("Generate cover letter", value=bool((app.get("inputs") or {}).get("cover_letter")),
                              key=f"{key}_rc_{aid}")
        b = st.columns(2)
        if b[0].button("🔁 Retry", type="primary", key=f"{key}_retry_{aid}", width="stretch",
                       help="Makes a new version using your feedback. Earlier versions are kept."):
            _retry(store, app, v, fb, model, intensity, cover, key)
        if serious and b[1].button("🛠 Fix the flagged fact-check issues", key=f"{key}_fix_{aid}",
                                   help="New version that reverts or removes only the flagged claims.",
                                   width="stretch"):
            ver = v.get("verification") or {}
            lines = [i.get("detail", "") for i in ver.get("rule_issues") or [] if i.get("severity") in ("high", "medium")]
            lines += [f"{i.get('claim')}: {i.get('problem')}" for i in ver.get("llm_issues") or []
                      if str(i.get("severity", "")).lower() in ("high", "medium")]
            fix = ("Fix these fact-check problems by reverting to the original facts/wording or removing the "
                   "unsupported claims. Change nothing else.\n- " + "\n- ".join(lines))
            _retry(store, app, v, fix, model, v["intensity"] or "Moderate", cover, key)


def _retry(store, app, v, feedback, model, intensity, cover, key) -> None:
    ss = st.session_state
    settings = Settings.from_dict(app.get("inputs"))
    settings.intensity, settings.cover_letter = intensity, cover
    llm = make_llm(model)
    vid = None
    try:
        with st.status("Creating a new version…", expanded=True) as status:
            data = generate_version(llm, original_text=app["original_resume_text"], resume_json=app["resume_json"],
                                    jd_analysis=app["jd_analysis"], company=app["company"],
                                    job_title=app["job_title"], settings=settings, previous=v["resume_json"],
                                    feedback=feedback, progress=status.write)
            vid = store.add_version(app["id"], {**data, **usage_totals(llm.usage), "model": llm.model})
            status.update(label="New version ready", state="complete", expanded=False)
    except LLMError as e:
        st.error(str(e))
    finally:
        record_usage(store, llm.usage, app["id"], vid, app["company"])
        ss.run_notices = llm.notices
    if vid:
        ss[f"{key}_sel_{app['id']}_pending"] = vid
        st.rerun()
