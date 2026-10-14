import streamlit as st

from core.llm_client import LLMError, is_reasoning
from core.parser import ParseError, extract_text
from core.pipeline import Settings, analyze_jd, extract_resume, generate_version, usage_totals
from core.tokens import count_tokens, estimate_run
from core.pipeline import MAX_JD_TOKENS
from ui import style, tour
from ui.common import INTENSITIES, INTENSITY_HELP, record_usage
from ui.results import render_results
from ui.sidebar import make_llm

REGIONS = ["US", "India", "UK/EU CV", "Gulf/Middle East"]
FILE_TYPES = ["pdf", "docx", "txt"]


def _upload_into(label: str, uploader_key: str, text_key: str, help: str | None = None) -> None:
    """File uploader that fills the editable text area `text_key` whenever a new file is chosen."""
    ss = st.session_state
    up = st.file_uploader(label, type=FILE_TYPES, key=uploader_key, help=help)
    if up is None:  # file removed: forget it, so a pasted resume isn't saved with an old file
        ss.pop(f"{uploader_key}_bytes", None)
        ss.pop(f"{uploader_key}_name", None)
    if up is not None and ss.get(f"{uploader_key}_id") != up.file_id:
        ss[f"{uploader_key}_id"] = up.file_id
        ss[f"{uploader_key}_bytes"], ss[f"{uploader_key}_name"] = up.getvalue(), up.name
        try:
            ss[text_key] = extract_text(up.name, up.getvalue())
            ss[f"{uploader_key}_err"] = None
        except ParseError as e:
            ss[f"{uploader_key}_err"] = str(e)
    if ss.get(f"{uploader_key}_err"):
        st.error(ss[f"{uploader_key}_err"])


def _resume_input() -> str:
    st.subheader("1 · Your current resume")
    _upload_into("Upload resume (PDF, DOCX or TXT)", "in_resume_file", "in_resume_text",
                 help="Your resume file. Its text appears below so you can check it; the file itself is kept in History.")
    return st.text_area("…or paste it here (edit if anything extracted badly)", key="in_resume_text", height=300,
                        help="This text is what Candor tailors. Fix anything that extracted oddly from a PDF.")


def _jd_input() -> tuple[str, str, str]:
    st.subheader("2 · Job description")
    _upload_into("Upload JD (PDF, DOCX or TXT)", "in_jd_file", "in_jd",
                 help="A saved copy of the job posting, if you have one.")
    jd = st.text_area("…or paste the full job description here", key="in_jd", height=190,
                      help="Paste the whole posting, including requirements and 'nice to have' sections.")
    c1, c2 = st.columns(2)
    company = c1.text_input("Company", key="in_company", placeholder="Auto-detected if blank",
                            help="Leave blank and Candor reads it from the job description.")
    title = c2.text_input("Job title", key="in_title", placeholder="Auto-detected if blank",
                          help="Leave blank and Candor reads it from the job description.")
    return jd, company, title


def _settings_input() -> tuple[Settings, bytes | None]:
    st.subheader("3 · Requirements & preferences")
    c1, c2, c3 = st.columns(3)
    region = c1.selectbox("Resume format / region", REGIONS, key="in_region",
                          help="Local conventions: what personal details to include, spelling, and A4 vs US Letter paper.")
    page_limit = c2.radio("Page limit", [1, 2], horizontal=True, key="in_pages",
                          format_func=lambda n: f"{n} page{'s' * (n > 1)}",
                          help="The PDF is fitted to this: wording is tightened first, then spacing, never below 9pt text.")
    intensity = c3.select_slider("Alteration intensity", INTENSITIES, value="Moderate", key="in_intensity", help=INTENSITY_HELP)

    c1, c2, c3 = st.columns(3)
    links = c1.checkbox("Include LinkedIn / GitHub / portfolio", value=True, key="in_links",
                        help="Keep your profile links in the contact line.")
    declaration = c2.checkbox("Add declaration statement", key="in_decl", help="Common for Indian resumes.")
    want_photo = c3.checkbox("Include photo", key="in_photo_on",
                             help="Common in the Gulf and parts of Europe; discouraged for US and UK roles.")
    photo = None
    if want_photo:
        if region in ("US", "UK/EU CV"):
            st.warning("Photos are discouraged for US/UK roles (bias concerns, some ATS reject images). Included anyway since you asked.")
        f = st.file_uploader("Photo (PNG/JPG, passport style)", type=["png", "jpg", "jpeg"], key="in_photo")
        if f:
            photo = f.getvalue()
            st.image(photo, width=90)

    c1, c2 = st.columns(2)
    extra = c1.text_area("Extra true facts to include (optional)", key="in_extra", height=110,
                         help="True details not in your resume. Candor may use them and won't flag them as invented.",
                         placeholder="Notice period: 30 days\nDate of birth: 01 Jan 2000\nWilling to relocate to Bengaluru")
    special = c2.text_area("Any other special requirements (optional)", key="in_special", height=110,
                           help="Instructions for the rewrite, e.g. what to emphasize or keep.",
                           placeholder="e.g. Emphasize my leadership experience; keep the Projects section; mention my AWS certification first")

    st.markdown("**✉️ Cover letter**")
    c1, c2, c3 = st.columns([1, 1, 2])
    cover = c1.checkbox("Generate cover letter", key="in_cover",
                        help="A 250–350 word letter using only facts from your resume. Adds one AI call.")
    tone = c2.selectbox("Tone", ["Professional", "Enthusiastic", "Concise"], key="in_tone", disabled=not cover,
                        help="How the letter sounds. The facts stay the same.")
    manager = c3.text_input("Hiring manager name (optional)", key="in_manager", disabled=not cover,
                            help="Used in the greeting; otherwise 'Dear Hiring Manager'.")

    settings = Settings(intensity=intensity, region=region, page_limit=page_limit, include_links=links,
                        include_photo=want_photo, include_declaration=declaration, extra_facts=extra,
                        special_instructions=special, cover_letter=cover, cover_tone=tone, hiring_manager=manager)
    return settings, photo


def _run(store, resume_text, jd, company, title, settings: Settings, photo) -> None:
    ss = st.session_state
    llm = make_llm(ss.model)
    app_id = vid = None
    anim = style.writing_animation()
    try:
        with st.status("Generating your tailored resume…", expanded=True) as status:
            status.write("📖 Reading your resume…")
            resume_json = extract_resume(llm, resume_text)
            status.write("🧭 Analyzing the job description and skill gaps…")
            analysis = analyze_jd(llm, jd, resume_text)
            company = company.strip() or analysis.get("company") or "Unknown company"
            title = title.strip() or analysis.get("job_title") or "Unknown role"
            version = generate_version(llm, original_text=resume_text, resume_json=resume_json,
                                       jd_analysis=analysis, company=company, job_title=title,
                                       settings=settings, progress=status.write)
            app_id = store.create_application(
                company=company, job_title=title, jd_text=jd, inputs=settings.to_dict(),
                original_resume_text=resume_text, resume_json=resume_json, jd_analysis=analysis, photo=photo,
                resume_file=ss.get("in_resume_file_bytes"), resume_filename=ss.get("in_resume_file_name"))
            vid = store.add_version(app_id, {**version, **usage_totals(llm.usage), "model": llm.model})
            status.update(label="Done!", state="complete", expanded=False)
    except LLMError as e:
        st.error(str(e))
    finally:
        anim.empty()
        record_usage(store, llm.usage, app_id, vid, company or None)
        ss.run_notices = llm.notices
    if vid:
        ss.current_app_id = app_id
        ss.just_generated = True
        st.rerun()


def render(store) -> None:
    ss = st.session_state
    guide_col, tour_col = st.columns([5, 1], vertical_alignment="center")
    with guide_col:
        style.guide(expanded=False)
    with tour_col:
        tour.render()

    left, right = st.columns(2, gap="medium")
    with left, st.container(border=True):
        resume_text = _resume_input()
    with right, st.container(border=True):
        jd, company, title = _jd_input()
    with st.container(border=True):
        settings, photo = _settings_input()

    with st.container(border=True):
        st.subheader("4 · Generate")
        if ss.get("model") and resume_text.strip() and jd.strip():
            est = estimate_run(resume_text, jd, ss.model, settings.cover_letter)
            cost = f"≈ ${est['cost']:.4f}" if est["cost"] is not None else "cost unknown"
            note = " (reasoning model: expect extra hidden 'thinking' tokens)" if is_reasoning(ss.model) else ""
            st.caption(f"Approx. before running: ~{est['input'] + est['output']:,} tokens · {cost} with "
                       f"**{ss.model}**{note}. Exact usage is shown after generation.")
        if jd.strip() and count_tokens(jd) > MAX_JD_TOKENS:
            st.caption(f"ℹ️ The JD is long, so only its first ~{MAX_JD_TOKENS:,} tokens are analyzed to fit model limits. "
                       "Remove company boilerplate if key requirements are near the end.")
        if st.button("✨ Generate Tailored Resume", type="primary", width="stretch", key="generate",
                     help="Reads your resume, analyses the job, tailors every section, fact-checks each change "
                          "and scores the ATS match."):
            missing = []
            if not ss.get("model_ok"):
                missing.append("a working API key and model (see the sidebar for what failed)")
            if len(resume_text.strip()) < 100:
                missing.append("your resume (upload or paste)")
            if len(jd.strip()) < 100:
                missing.append("the full job description (upload or paste)")
            if settings.include_photo and not photo:
                missing.append("a photo (or untick 'Include photo')")
            if missing:
                st.warning("Please add: " + "; ".join(missing) + ".")
            else:
                _run(store, resume_text, jd, company, title, settings, photo)

    for n in ss.pop("run_notices", None) or []:
        st.warning(f"🛟 {n}")
    if ss.get("current_app_id"):
        st.markdown('<div id="results"></div>', unsafe_allow_html=True)
        if ss.pop("just_generated", False):
            st.toast("Your tailored resume is ready!", icon="✅")
            # fixed, app-authored script (never user content), so a same-origin iframe is safe here
            st.iframe("<script>window.parent.document.getElementById('results')"
                      "?.scrollIntoView({behavior: 'smooth'});</script>", height=1)
        render_results(store, ss.current_app_id, key="cur")
