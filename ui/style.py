"""Look and feel: dark palette, hover effects, the welcome guide and the 'writing your resume' animation.

Colors mirror .streamlit/config.toml. Every animation is switched off for visitors who ask their system for
reduced motion.
"""
import streamlit as st

CSS = """<style>
:root{
  --rr-bg:#0B1020; --rr-card:#121A2E; --rr-card-hi:#18223A; --rr-border:#2A3550; --rr-text:#E5E7EB;
  --rr-muted:#94A3B8; --rr-violet:#8B5CF6; --rr-indigo:#6366F1; --rr-fuchsia:#D946EF; --rr-teal:#2DD4BF;
  --rr-grad:linear-gradient(120deg,#6366F1 0%,#8B5CF6 45%,#D946EF 100%);
}
/* soft glow behind the page */
[data-testid="stAppViewContainer"]{
  background:radial-gradient(1200px 600px at 10% -10%,rgba(99,102,241,.16),transparent 60%),
             radial-gradient(900px 500px at 100% 0%,rgba(217,70,239,.10),transparent 55%),var(--rr-bg)}
[data-testid="stHeader"]{background:transparent}

/* banner: slowly drifting gradient */
.rr-banner{background:var(--rr-grad);background-size:200% 200%;animation:rr-drift 12s ease infinite;color:#fff;
  padding:1.2rem 1.5rem;border-radius:1rem;margin-bottom:.9rem;box-shadow:0 10px 30px rgba(139,92,246,.35)}
.rr-banner h1{color:#fff;font-size:1.8rem;margin:0;padding:0;letter-spacing:.2px}
.rr-banner p{color:#F5F3FF;margin:.25rem 0 0 0;font-size:.98rem;opacity:.95}
@keyframes rr-drift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}

/* bordered cards: dark glass that lifts and glows on hover */
[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(180deg,var(--rr-card-hi),var(--rr-card));
  border-color:var(--rr-border)!important;transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease;
  animation:rr-rise .35s ease-out both}
[data-testid="stVerticalBlockBorderWrapper"]:hover{transform:translateY(-2px);border-color:rgba(139,92,246,.55)!important;
  box-shadow:0 8px 28px rgba(139,92,246,.18)}
@keyframes rr-rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

/* headings */
h3{color:#C4B5FD}
h4{color:#E9D5FF}

/* main tabs: pill style with a gradient underline */
button[data-baseweb="tab"]{border-radius:.6rem .6rem 0 0;transition:background .15s ease,color .15s ease}
button[data-baseweb="tab"]:hover{background:rgba(139,92,246,.12);color:#DDD6FE}
button[data-baseweb="tab"][aria-selected="true"]{color:#F5F3FF}
[data-baseweb="tab-highlight"]{background:var(--rr-grad)!important;height:3px}

/* buttons */
button[kind="primary"],[data-testid="stBaseButton-primary"]{background:var(--rr-grad)!important;background-size:200% 200%!important;
  border:none!important;font-size:1.05rem!important;font-weight:600!important;padding:.6rem 1rem!important;
  box-shadow:0 6px 20px rgba(139,92,246,.35);transition:transform .15s ease,box-shadow .15s ease,background-position .4s ease}
button[kind="primary"]:hover,[data-testid="stBaseButton-primary"]:hover{transform:translateY(-1px);background-position:100% 50%!important;
  box-shadow:0 10px 28px rgba(217,70,239,.40)}
[data-testid="stBaseButton-secondary"],[data-testid="stDownloadButton"] button{transition:all .15s ease}
[data-testid="stBaseButton-secondary"]:hover,[data-testid="stDownloadButton"] button:hover{border-color:var(--rr-violet)!important;
  color:#EDE9FE!important;box-shadow:0 0 0 3px rgba(139,92,246,.18);transform:translateY(-1px)}

/* metrics as small colored tiles */
[data-testid="stMetric"]{background:rgba(99,102,241,.08);border:1px solid var(--rr-border);border-left:4px solid var(--rr-violet);
  border-radius:.7rem;padding:.6rem .8rem;transition:border-color .15s ease}
[data-testid="stMetric"]:hover{border-left-color:var(--rr-fuchsia)}
/* the sidebar is narrow: smaller tiles so labels and values aren't cut off */
[data-testid="stSidebar"] [data-testid="stMetric"]{padding:.45rem .55rem;border-left-width:3px}
[data-testid="stSidebar"] [data-testid="stMetricValue"]{font-size:1.25rem}
[data-testid="stSidebar"] [data-testid="stMetricLabel"] p{font-size:.78rem}
[data-testid="stMetricDelta"] svg{display:inline}

/* inputs: violet focus ring */
textarea:focus,input:focus{box-shadow:0 0 0 2px rgba(139,92,246,.45)!important}
[data-testid="stFileUploaderDropzone"]{border:1.5px dashed rgba(139,92,246,.55)!important;background:rgba(139,92,246,.06)!important;
  transition:background .15s ease}
[data-testid="stFileUploaderDropzone"]:hover{background:rgba(139,92,246,.12)!important}

/* expanders */
[data-testid="stExpander"] details{border-color:var(--rr-border)!important;border-radius:.8rem}
[data-testid="stExpander"] summary:hover{color:#DDD6FE}

/* welcome guide */
.rr-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:.8rem;margin:.3rem 0 .6rem}
.rr-step{position:relative;background:var(--rr-card-hi);border:1px solid var(--rr-border);border-radius:.9rem;padding:.9rem;
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;animation:rr-rise .45s ease-out both}
.rr-step:nth-child(2){animation-delay:.07s}.rr-step:nth-child(3){animation-delay:.14s}.rr-step:nth-child(4){animation-delay:.21s}
.rr-step:hover{transform:translateY(-3px);border-color:var(--rr-violet);box-shadow:0 10px 26px rgba(139,92,246,.22)}
.rr-step .n{display:inline-flex;width:1.7rem;height:1.7rem;border-radius:50%;align-items:center;justify-content:center;
  background:var(--rr-grad);color:#fff;font-weight:700;font-size:.85rem;margin-right:.4rem}
.rr-step .t{font-weight:700;color:#F5F3FF}
.rr-step p{color:var(--rr-muted);font-size:.86rem;margin:.45rem 0 0;line-height:1.4}
.rr-step .ico{position:absolute;right:.8rem;top:.7rem;font-size:1.3rem;opacity:.9}
.rr-tip{color:var(--rr-muted);font-size:.85rem}
.rr-tip b{color:#C4B5FD}

/* "writing your resume" animation */
.rr-writer{display:flex;gap:2.2rem;align-items:center;justify-content:center;padding:1.4rem .5rem 1rem;flex-wrap:wrap}
.rr-laptop{position:relative;width:190px}
.rr-screen{height:118px;background:#0F172A;border:7px solid #334155;border-bottom-width:9px;border-radius:.6rem .6rem .2rem .2rem;
  padding:.55rem .6rem;overflow:hidden;box-shadow:0 0 24px rgba(99,102,241,.35)}
.rr-code{height:7px;border-radius:4px;margin:.38rem 0;background:linear-gradient(90deg,#6366F1,#2DD4BF);width:0;
  animation:rr-type 3.2s steps(18) infinite}
.rr-code:nth-child(2){animation-delay:.5s;background:linear-gradient(90deg,#D946EF,#8B5CF6)}
.rr-code:nth-child(3){animation-delay:1s}
.rr-code:nth-child(4){animation-delay:1.5s;background:linear-gradient(90deg,#F59E0B,#D946EF)}
.rr-code:nth-child(5){animation-delay:2s}
.rr-cursor{display:inline-block;width:7px;height:11px;background:#E5E7EB;animation:rr-blink .8s steps(1) infinite}
.rr-base{height:11px;width:228px;margin-left:-19px;background:linear-gradient(180deg,#475569,#1E293B);border-radius:0 0 .7rem .7rem}
.rr-flow{font-size:1.5rem;color:#C4B5FD;animation:rr-pulse 1.4s ease-in-out infinite}
.rr-paper{position:relative;width:170px;height:212px;background:#F8FAFC;border-radius:.4rem;padding:1.05rem .95rem;
  box-shadow:0 14px 36px rgba(0,0,0,.45);transform:rotate(-2deg)}
.rr-paper .h{height:11px;width:55%;border-radius:4px;background:#1F3A5F;margin-bottom:.75rem}
.rr-ink{height:6px;border-radius:3px;background:#94A3B8;margin:.55rem 0;width:0;animation:rr-ink 4.8s ease-in-out infinite}
.rr-ink:nth-of-type(2){animation-delay:.35s}.rr-ink:nth-of-type(3){animation-delay:.7s}.rr-ink:nth-of-type(4){animation-delay:1.05s}
.rr-ink:nth-of-type(5){animation-delay:1.4s}.rr-ink:nth-of-type(6){animation-delay:1.75s}.rr-ink:nth-of-type(7){animation-delay:2.1s}
.rr-ink:nth-of-type(8){animation-delay:2.45s}
.rr-pen{position:absolute;font-size:1.7rem;left:30px;top:30px;animation:rr-pen 4.8s ease-in-out infinite;
  filter:drop-shadow(0 3px 4px rgba(0,0,0,.35))}
.rr-writer-cap{text-align:center;color:#DDD6FE;font-weight:600;margin-top:.2rem}
.rr-writer-cap span{color:var(--rr-muted);font-weight:400}
@keyframes rr-type{0%{width:0}60%{width:92%}100%{width:92%}}
@keyframes rr-ink{0%{width:0}55%{width:var(--w,88%)}100%{width:var(--w,88%)}}
@keyframes rr-pen{0%{transform:translate(0,0) rotate(0)}15%{transform:translate(95px,8px) rotate(8deg)}
  30%{transform:translate(10px,40px) rotate(-4deg)}45%{transform:translate(100px,58px) rotate(8deg)}
  60%{transform:translate(15px,92px) rotate(-4deg)}75%{transform:translate(95px,118px) rotate(8deg)}100%{transform:translate(0,0)}}
@keyframes rr-blink{50%{opacity:0}}
@keyframes rr-pulse{0%,100%{opacity:.35;transform:translateX(-4px)}50%{opacity:1;transform:translateX(4px)}}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
  .rr-code,.rr-ink{width:85%!important}
}
</style>"""

BANNER = """<div class="rr-banner"><h1>📄 Candor</h1>
<p>Tailored resumes. Every word true. ATS-friendly tailoring for any job description, with an optional cover letter.</p></div>"""

GUIDE = """<div class="rr-steps">
  <div class="rr-step" title="PDF, DOCX or TXT. You can also paste the text and fix anything that extracted badly.">
    <span class="ico">📄</span><span class="n">1</span><span class="t">Add your resume</span>
    <p>Upload a PDF, DOCX or TXT, or paste the text. Candor reads it exactly as written.</p></div>
  <div class="rr-step" title="Paste the whole posting: company and role are detected automatically.">
    <span class="ico">📋</span><span class="n">2</span><span class="t">Paste the job</span>
    <p>Drop in the full job description. Company and role are detected for you.</p></div>
  <div class="rr-step" title="Region format, page limit, how much to rewrite, and an optional cover letter.">
    <span class="ico">🎛️</span><span class="n">3</span><span class="t">Choose settings</span>
    <p>Pick the format, page limit and how strongly to tailor. Add a cover letter if you like.</p></div>
  <div class="rr-step" title="Every change is fact-checked against your original resume before you see it.">
    <span class="ico">✨</span><span class="n">4</span><span class="t">Tailor & download</span>
    <p>Get a one-page PDF/DOCX, the ATS match, every change with its reason, and a fact check.</p></div>
</div>
<div class="rr-tip"><b>Why it's honest:</b> companies, titles, dates, degrees and numbers are locked. Skills you don't have
are listed as gaps, never added, and anything the AI drafts that isn't in your resume is caught and corrected.
<b>Tip:</b> hover over any ⓘ for what a setting does.</div>"""

WRITER = """<div class="rr-writer" role="img" aria-label="Animation: your resume is being written">
  <div class="rr-laptop"><div class="rr-screen">
    <div class="rr-code"></div><div class="rr-code"></div><div class="rr-code"></div><div class="rr-code"></div>
    <div class="rr-code"></div><span class="rr-cursor"></span></div><div class="rr-base"></div></div>
  <div class="rr-flow">➜</div>
  <div class="rr-paper"><div class="h"></div>
    <div class="rr-ink" style="--w:92%"></div><div class="rr-ink" style="--w:78%"></div><div class="rr-ink" style="--w:86%"></div>
    <div class="rr-ink" style="--w:64%"></div><div class="rr-ink" style="--w:90%"></div><div class="rr-ink" style="--w:72%"></div>
    <div class="rr-ink" style="--w:84%"></div>
    <div class="rr-pen">✒️</div></div>
</div>
<div class="rr-writer-cap">Candor is writing your resume… <span>usually 20–40 seconds</span></div>"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def banner() -> None:
    st.markdown(BANNER, unsafe_allow_html=True)


def guide(expanded: bool) -> None:
    """'How Candor works': open for first-time visitors, tucked away once there's history."""
    with st.expander("👋 New here? How Candor works", expanded=expanded):
        st.markdown(GUIDE, unsafe_allow_html=True)


def writing_animation():
    """Show the laptop-and-paper animation; returns the placeholder so the caller can clear it when done."""
    slot = st.empty()
    slot.markdown(WRITER, unsafe_allow_html=True)
    return slot
