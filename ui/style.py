import streamlit as st

CSS = """<style>
/* Header banner */
.rr-banner{background:linear-gradient(120deg,#4F46E5 0%,#7C3AED 55%,#A855F7 100%);color:#fff;
  padding:1.1rem 1.4rem;border-radius:0.9rem;margin-bottom:0.8rem;box-shadow:0 6px 18px rgba(79,70,229,.25)}
.rr-banner h1{color:#fff;font-size:1.7rem;margin:0;padding:0}
.rr-banner p{color:#E0E7FF;margin:0.2rem 0 0 0;font-size:0.95rem}

/* Bordered cards: white on the tinted page with a soft shadow */
[data-testid="stVerticalBlockBorderWrapper"]{background:#FFFFFF;box-shadow:0 2px 10px rgba(30,41,59,.06)}

/* Checkboxes and radios: visible unchecked boxes, darker labels */
[data-baseweb="checkbox"] > span:first-child{border:2px solid #64748B !important;}
[data-baseweb="radio"] > div:first-child{border:2px solid #64748B !important;}
[data-testid="stCheckbox"] label p,[data-testid="stRadio"] label p{color:#1E293B;font-weight:500}

/* Primary button: gradient and larger text */
button[kind="primary"],[data-testid="stBaseButton-primary"]{
  background:linear-gradient(120deg,#4F46E5,#7C3AED) !important;border:none !important;
  font-size:1.05rem !important;font-weight:600 !important;padding:0.6rem 1rem !important}
button[kind="primary"]:hover,[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.08)}

/* Section subheaders in indigo */
h3{color:#3730A3}
</style>"""

BANNER = """<div class="rr-banner"><h1>📄 Resume Redrafter</h1>
<p>Tailor your resume to any job description: ATS-friendly, honest, with an optional cover letter.</p></div>"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def banner() -> None:
    st.markdown(BANNER, unsafe_allow_html=True)
