import io
import zipfile

import pandas as pd
import streamlit as st

from core.renderer import resume_to_text, to_docx
from core.tailor import change_report
from ui.common import safe_filename
from ui.results import render_results


def _build_zip(store, apps: list[dict]) -> bytes:
    """One folder per application with the JD plus the final (or latest) version."""
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
            folder = safe_filename(app["created_at"][:10], app["company"], app["job_title"])
            z.writestr(f"{folder}/job_description.txt", app["jd_text"] or "")
            z.writestr(f"{folder}/resume_v{v['version_no']}.docx",
                       to_docx(v["resume_json"], photo, inputs.get("region", "US") != "US"))
            z.writestr(f"{folder}/resume_v{v['version_no']}.txt", resume_to_text(v["resume_json"]))
            if v.get("cover_letter"):
                z.writestr(f"{folder}/cover_letter_v{v['version_no']}.txt", v["cover_letter"])
            z.writestr(f"{folder}/changes_v{v['version_no']}.txt",
                       change_report(v.get("change_log") or [], (v.get("ats_detail") or {}).get("stats")))
    return buf.getvalue()


def render(store) -> None:
    ss = st.session_state
    st.header("Application history")
    apps = store.list_applications()
    if not apps:
        st.info("No redrafts yet. Your tailored resumes will appear here.")
        return

    q = st.text_input("🔎 Search by company or role", key="hist_q").strip().lower()
    shown = [a for a in apps if q in f"{a['company']} {a['job_title']}".lower()] if q else apps
    df = pd.DataFrame([{
        "Date": a["created_at"][:16].replace("T", " "), "Company": a["company"], "Role": a["job_title"],
        "Versions": a["versions"], "Final": f"v{a['final_version']}" if a["final_version"] else "–",
        "Best ATS %": a["best_ats"], "Cost ($)": round(a["cost_usd"] or 0, 4),
    } for a in shown])
    st.dataframe(df, width="stretch", hide_index=True)

    c1, c2 = st.columns([3, 1])
    with c2:
        if st.button("📦 Prepare ZIP of all", width="stretch"):
            with st.spinner("Building ZIP…"):
                ss.hist_zip = _build_zip(store, apps)
        if ss.get("hist_zip"):
            st.download_button("⬇️ Download ZIP", ss.hist_zip, "resume_redrafter_history.zip",
                               "application/zip", width="stretch")
    if not shown:
        st.warning("No applications match your search.")
        return

    labels = {a["id"]: f"{a['company']} — {a['job_title']}  ({a['created_at'][:10]})" for a in shown}
    with c1:
        app_id = st.selectbox("Open application", list(labels), format_func=labels.get, key="hist_app")
    app = store.get_application(app_id)
    if not app:
        return
    with st.expander("📋 Job description & settings used"):
        st.text(app["jd_text"])
        st.json(app.get("inputs") or {}, expanded=False)
    render_results(store, app_id, key="hist")

    with st.expander("🗑️ Delete this application"):
        st.caption("Removes the JD and every version. Token usage stays in the Usage tab.")
        sure = st.checkbox("Yes, delete it permanently", key=f"hist_del_ok_{app_id}")
        if st.button("Delete", disabled=not sure, key=f"hist_del_{app_id}"):
            store.delete_application(app_id)
            if ss.get("current_app_id") == app_id:
                ss.current_app_id = None
            ss.pop("hist_zip", None)
            st.rerun()
