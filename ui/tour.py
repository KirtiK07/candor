"""Guided tour: popups that point at each control in turn (Next / Back / Skip), built on driver.js.

It starts by itself on a visitor's first visit (remembered in their browser) and replays from the
"Take the tour" button. Steps whose element isn't on screen (e.g. a collapsed sidebar on a phone) are skipped.
"""
import json
import time

import streamlit as st

DRIVER = "https://cdn.jsdelivr.net/npm/driver.js@1.3.1/dist"

# (CSS selector or "" for a centered message, title, text)
STEPS = [
    ("", "Welcome to Candor 👋", "A one-minute tour of how it works. Use <b>Next</b> and <b>Back</b> (or the arrow "
     "keys), and <b>Esc</b> to skip. You can replay it any time from <b>🧭 Take the tour</b>."),
    (".st-key-provider", "AI provider", "The AI service that writes your resume. If it runs out of quota mid-run, "
     "Candor switches to the next one automatically."),
    (".st-key-model", "Model", "Pre-selected: the best model that passed a live test with your key."),
    (".st-key-in_resume_file", "1 · Upload your resume", "PDF, DOCX or TXT. The original file is kept in History so "
     "you can download it again."),
    (".st-key-in_resume_text", "Check the extracted text", "This text is what gets tailored. Fix anything that came "
     "out oddly from the PDF, or paste your resume here instead."),
    (".st-key-in_jd", "2 · Paste the job description", "Paste the whole posting, including requirements and "
     "'nice to have'. You can also upload it as a file just above."),
    (".st-key-in_company", "Company & role", "Leave these blank: Candor reads them from the job description."),
    (".st-key-in_region", "Resume format", "Local conventions: which personal details to include, spelling, and "
     "A4 vs US Letter."),
    (".st-key-in_pages", "Page limit", "The PDF is fitted to this. Wording is tightened first, then spacing, never "
     "below 9pt text."),
    (".st-key-in_intensity", "How much to tailor", "<b>Light</b> touches the summary and a few bullets, "
     "<b>Strong</b> reworks nearly everything. Facts stay locked at every level."),
    (".st-key-in_extra", "Extra true facts", "Things that are true but not on your resume, like notice period. Candor "
     "may use them and won't flag them as invented."),
    (".st-key-in_cover", "Cover letter", "Tick to also get a short letter built only from your real experience."),
    (".st-key-generate", "3 · Generate", "Reads your resume, analyses the job, tailors each section, fact-checks "
     "every change and scores the ATS match. Usually 20–40 seconds."),
    ('[data-testid="stTab"]:nth-child(2)', "History", "Every application: your original resume, the job and the "
     "tailored resume side by side, all downloadable. Kept for 30 days."),
    ('[data-testid="stTab"]:nth-child(3)', "Usage", "Tokens and cost for every AI call, by model, day and company."),
    ('[data-testid="stTab"]:nth-child(4)', "Settings", "Model prices, where history is stored, and privacy details."),
    ("", "You're all set ✨", "Upload your resume, paste a job and press <b>Generate</b>. Hover over any ⓘ for help."),
]

THEME = """
/* above Streamlit's sidebar and header, so the whole page dims */
.driver-overlay{z-index:1000000!important}
.driver-popover{z-index:1000001!important}
.driver-popover.candor-pop{background:#151C2F;color:#E5E7EB;border:1px solid #8B5CF6;border-radius:14px;
  box-shadow:0 18px 50px rgba(139,92,246,.35);max-width:340px}
.driver-popover.candor-pop .driver-popover-title{font-size:16px;font-weight:700;color:#F5F3FF}
.driver-popover.candor-pop .driver-popover-description{color:#CBD5E1;font-size:14px;line-height:1.5}
.driver-popover.candor-pop .driver-popover-progress-text{color:#94A3B8}
.driver-popover.candor-pop button{background:#1E293B;color:#E5E7EB;border:1px solid #334155;text-shadow:none;
  border-radius:8px;padding:5px 12px;font-size:13px}
.driver-popover.candor-pop .driver-popover-next-btn{background:linear-gradient(120deg,#6366F1,#8B5CF6,#D946EF);
  border:none;color:#fff;font-weight:600}
.driver-popover.candor-pop .driver-popover-close-btn{background:transparent;border:none;color:#94A3B8}
.driver-popover.candor-pop .driver-popover-arrow-side-left.driver-popover-arrow{border-left-color:#151C2F}
.driver-popover.candor-pop .driver-popover-arrow-side-right.driver-popover-arrow{border-right-color:#151C2F}
.driver-popover.candor-pop .driver-popover-arrow-side-top.driver-popover-arrow{border-top-color:#151C2F}
.driver-popover.candor-pop .driver-popover-arrow-side-bottom.driver-popover-arrow{border-bottom-color:#151C2F}
"""

# Runs in a same-origin iframe and drives the parent page. Only app-authored content goes in here.
SCRIPT = """<script>
(function () {
  const P = window.parent, D = P.document, force = %(force)s;
  const DONE = "candorTourDone";
  let seen = false;
  try { seen = P.localStorage.getItem(DONE) === "1"; } catch (e) {}
  if (!force && (seen || P.__candorTourShown)) return;
  P.__candorTourShown = true;

  function load(tag, attrs) {
    return new Promise(function (ok) {
      if (D.querySelector(tag + "[data-candor-tour]")) return ok();
      const el = D.createElement(tag);
      Object.assign(el, attrs); el.setAttribute("data-candor-tour", "1"); el.onload = ok;
      if (tag === "style") { el.textContent = attrs.textContent; D.head.appendChild(el); return ok(); }
      D.head.appendChild(el);
    });
  }
  function visible(el) { return el && el.offsetParent !== null && el.getBoundingClientRect().width > 0; }

  Promise.all([
    load("link", {rel: "stylesheet", href: "%(base)s/driver.css"}),
    load("style", {textContent: %(theme)s}),
    P.driver ? Promise.resolve() : load("script", {src: "%(base)s/driver.js.iife.js"}),
  ]).then(function () {
    // wait until Streamlit has drawn the controls
    let tries = 0;
    (function start() {
      if (!D.querySelector(".st-key-generate") && tries++ < 40) return setTimeout(start, 250);
      const steps = %(steps)s.map(function (s) {
        const el = s[0] ? D.querySelector(s[0]) : null;
        if (s[0] && !visible(el)) return null;
        // sidebar items: popup to the right; the Generate button: above; everything else: below
        const inSidebar = el && el.closest('[data-testid="stSidebar"]');
        const side = inSidebar ? "right" : (s[0] === ".st-key-generate" ? "top" : "bottom");
        const step = {popover: {title: s[1], description: s[2], side: side, align: "start"}};
        if (el) step.element = el;
        return step;
      }).filter(Boolean);
      const tour = P.driver.js.driver({
        showProgress: true, progressText: "{{current}} of {{total}}", animate: true, smoothScroll: true,
        allowClose: true, overlayColor: "#05070f", overlayOpacity: 0.72, stagePadding: 6, stageRadius: 10,
        popoverClass: "candor-pop", nextBtnText: "Next →", prevBtnText: "← Back", doneBtnText: "Let's go",
        steps: steps,
        onDestroyed: function () { try { P.localStorage.setItem(DONE, "1"); } catch (e) {} },
      });
      tour.drive();
    })();
  });
})();
</script>"""


def render() -> None:
    """Tour button plus the script that runs the tour (automatically once per browser, or when asked)."""
    ss = st.session_state
    force = bool(ss.pop("tour_requested", False))
    if st.button("🧭 Take the tour", key="tour_btn",
                 help="Step-by-step popups showing what each part of Candor does."):
        ss.tour_requested = True
        st.rerun()
    script = SCRIPT % {"force": "true" if force else "false", "base": DRIVER, "theme": json.dumps(THEME),
                       "steps": json.dumps(STEPS)}
    if force:  # a fresh iframe each time the button is pressed, so the tour starts again
        script += f"<!-- {time.time()} -->"
    # fixed, app-authored script (never user content), so a same-origin iframe is safe here
    st.iframe(script, height=1)
