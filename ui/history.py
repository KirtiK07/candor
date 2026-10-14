"""History: one card per application with the original resume, the JD and the tailored resume, all downloadable.

Files are built only when a download button is clicked, so the page stays fast however long the history gets.
The full results view (diff, fact check, retry) opens on demand.
"""
import io
import mimetypes
import zipfile
from datetime import datetime, timedelta, timezone

import streamlit as st

from core.config import setting
from core.renderer import cover_letter_to_pdf, resume_to_markdown, resume_to_text, to_docx, to_pdf
from core.tailor import change_report
from ui.common import fmt_time, safe_filename, to_ist
from ui.results import render_results

PAGE = 10


def retention_days() -> int:
    """Days to keep history (HISTORY_RETENTION_DAYS, default 30; 0 keeps it forever)."""
    try:
        return max(0, int(setting("HISTORY_RETENTION_DAYS", 30) or 0))
    except (TypeError, ValueError):
        return 30


@st.cache_data(ttl=3600, show_spinner=False)
def purge_old(_store, days: int) -> int:
    """Delete applications older than `days`. Runs at most once an hour; returns how many were removed."""
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return _store.delete_older_than(cutoff.isoformat(timespec="seconds"))
BOX_HEIGHT = 300
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _build_zip(store, apps: list[dict]) -> bytes:
    """One folder per application with the original resume, the JD and the final (or latest) version."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in apps:
            app = store.get_application(a["id"])
            versions = store.get_versions(a["id"])
            if not app or not versions:
                continue
            v = next((x for x in versions if x["is_final"]), versions[-1])
            inputs = app.get("inputs") or {}
            photo = app.get("photo") if inputs.get("include_photo") else None
            a4, n = inputs.get("region", "US") != "US", v["version_no"]
            day = to_ist(app["created_at"])
            folder = safe_filename(day.strftime("%Y-%m-%d") if day else app["created_at"][:10], app["company"],
                                   app["job_title"])
            if app.get("resume_file"):
                z.writestr(f"{folder}/original_{safe_filename(app.get('resume_filename') or 'resume')}",
                           app["resume_file"])
            z.writestr(f"{folder}/original_resume.txt", app.get("original_resume_text") or "")
            z.writestr(f"{folder}/job_description.txt", app["jd_text"] or "")
            z.writestr(f"{folder}/tailored_resume_v{n}.pdf",
                       to_pdf(v["resume_json"], photo, a4, int(inputs.get("page_limit", 1)))[0])
            z.writestr(f"{folder}/tailored_resume_v{n}.docx", to_docx(v["resume_json"], photo, a4))
            if v.get("cover_letter"):
                z.writestr(f"{folder}/cover_letter_v{n}.pdf", cover_letter_to_pdf(v["cover_letter"], a4))
            z.writestr(f"{folder}/changes_v{n}.txt",
                       change_report(v.get("change_log") or [], (v.get("ats_detail") or {}).get("stats")))
    return buf.getvalue()


def _card(store, summary: dict) -> None:
    ss = st.session_state
    aid = summary["id"]
    app = store.get_application(aid)
    versions = store.get_versions(aid)
    if not app or not versions:
        return
    inputs = app.get("inputs") or {}
    photo = app.get("photo") if inputs.get("include_photo") else None
    a4, limit = inputs.get("region", "US") != "US", int(inputs.get("page_limit", 1))

    with st.container(border=True):
        head, pick = st.columns([3, 2])
        head.markdown(f"#### {app['job_title']} · {app['company']}")
        by_no = {v["version_no"]: v for v in versions}
        default = next((v["version_no"] for v in versions if v["is_final"]), versions[-1]["version_no"])
        if len(versions) > 1:
            n = pick.radio("Version", list(by_no), index=list(by_no).index(default), horizontal=True,
                           key=f"h_ver_{aid}", format_func=lambda x: f"v{x}" + (" ⭐" if by_no[x]["is_final"] else ""))
        else:
            n = default
        v = by_no[n]
        head.caption(f"{fmt_time(app['created_at'])}  ·  ATS match {v['ats_before']}% → **{v['ats_after']}%**"
                     + (f"  ·  {len(versions)} versions" if len(versions) > 1 else ""))

        base = safe_filename(v["resume_json"].get("name", ""), app["company"], app["job_title"], f"v{n}")
        orig, jd, new = st.columns(3)
        with orig:
            st.markdown("**📄 Original resume**")
            with st.container(height=BOX_HEIGHT):
                st.text(app.get("original_resume_text") or "")
            if app.get("resume_file"):  # exactly the file that was uploaded
                fname = app.get("resume_filename") or "resume"
                st.download_button(f"⬇️ {fname}", app["resume_file"], fname,
                                   mimetypes.guess_type(fname)[0] or "application/octet-stream",
                                   key=f"h_orig_{aid}", width="stretch")
            else:  # pasted text, or saved before uploaded files were kept
                st.download_button("⬇️ Original (.txt)", app.get("original_resume_text") or "",
                                   f"{base}_original.txt", key=f"h_orig_{aid}", width="stretch")
        with jd:
            st.markdown("**📋 Job description**")
            with st.container(height=BOX_HEIGHT):
                st.text(app.get("jd_text") or "")
            st.download_button("⬇️ Job description (.txt)", app.get("jd_text") or "", f"{base}_jd.txt",
                               key=f"h_jd_{aid}", width="stretch")
        with new:
            st.markdown("**✨ Tailored resume**")
            with st.container(height=BOX_HEIGHT):
                st.markdown(resume_to_markdown(v["resume_json"]))
            r = v["resume_json"]
            d1, d2 = st.columns(2)
            d1.download_button("⬇️ PDF", lambda r=r: to_pdf(r, photo, a4, limit)[0], f"{base}.pdf",
                               "application/pdf", key=f"h_pdf_{aid}_{n}", width="stretch",
                               help="Tailored resume as a PDF fitted to your page limit.")
            d2.download_button("⬇️ DOCX", lambda r=r: to_docx(r, photo, a4), f"{base}.docx", DOCX_MIME,
                               help="Tailored resume as an editable Word file (best for ATS).",
                               key=f"h_docx_{aid}_{n}", width="stretch")
            if v.get("cover_letter"):
                st.download_button("⬇️ Cover letter (PDF)", lambda t=v["cover_letter"]: cover_letter_to_pdf(t, a4),
                                   f"{base}_cover_letter.pdf", "application/pdf", key=f"h_cl_{aid}_{n}",
                                   width="stretch")

        more, delete = st.columns([3, 1])
        details = more.toggle("Show details: changes, diff, fact check, retry", key=f"h_more_{aid}")
        with delete.popover("🗑️ Delete", width="stretch"):
            st.caption("Removes this application and every version. Token usage stays in the Usage tab.")
            if st.button("Delete permanently", type="primary", key=f"h_del_{aid}"):
                store.delete_application(aid)
                if ss.get("current_app_id") == aid:
                    ss.current_app_id = None
                st.rerun()
        if details:
            render_results(store, aid, key="hist")


def render(store) -> None:
    ss = st.session_state
    st.header("History")
    apps = store.list_applications()
    if not apps:
        st.info("No tailored resumes yet. They will appear here.")
        return

    days = retention_days()
    if days:
        st.caption(f"🕒 History older than {days} days is deleted automatically.")
    search, zip_col, clear_col = st.columns([4, 2, 2])
    q = search.text_input("🔎 Search by company or role", key="hist_q", label_visibility="collapsed",
                          placeholder="🔎 Search by company or role").strip().lower()
    zip_col.download_button("📦 Download all (ZIP)", lambda: _build_zip(store, apps), "candor_history.zip",
                            "application/zip", width="stretch", key="hist_zip",
                            help="One folder per application: original resume, JD, tailored PDF/DOCX, cover letter.")
    with clear_col.popover("🧹 Clear all history", width="stretch"):
        st.warning(f"This permanently deletes all {len(apps)} application(s): resumes, job descriptions, every "
                   "version and cover letter. Token usage stays in the Usage tab.")
        confirm = st.text_input("Type DELETE to confirm", key="hist_clear_confirm")
        if st.button("Delete everything", type="primary", key="hist_clear", disabled=confirm.strip() != "DELETE"):
            n = store.clear_history()
            ss.current_app_id = None
            ss.pop("hist_clear_confirm", None)
            st.toast(f"Deleted {n} application(s).", icon="🧹")
            st.rerun()
    shown = [a for a in apps if q in f"{a['company']} {a['job_title']}".lower()] if q else apps
    if not shown:
        st.warning("No applications match your search.")
        return
    st.caption(f"{len(shown)} application{'s' * (len(shown) != 1)}, newest first")

    limit = ss.get("hist_limit", PAGE)
    for a in shown[:limit]:
        _card(store, a)
    if len(shown) > limit and st.button(f"Show {min(PAGE, len(shown) - limit)} more", key="hist_more"):
        ss.hist_limit = limit + PAGE
        st.rerun()
