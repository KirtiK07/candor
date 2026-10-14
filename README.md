# 📄 Candor

**Tailored resumes. Every word true.**


Tailor your resume to any job description so it's ATS-friendly, **without inventing anything**.
Paste a JD, upload your resume, and get a tailored DOCX/PDF plus an optional cover letter, an ATS match score,
a diff of every change, and a fact-check report.

## Features
- **Inputs:** resume (PDF/DOCX/TXT or paste), JD, company/title (auto-detected), region format (US / India / UK-EU / Gulf),
  page limit, alteration intensity (Light / Moderate / Strong), links on/off, photo, declaration, extra true facts
  (notice period, DOB…), free-text special requirements, cover letter checkbox with tone and hiring manager.
- **Honest tailoring pipeline:** extract resume → analyze JD, gaps and keyword evidence → rewrite under hard rules →
  fit to the page limit → AI fact check of every change → automatic repair of flagged claims → rule-based fact check →
  ATS score → cover letter. Only JD terms the resume genuinely supports are worked in; skills you don't have are listed
  as gaps and blocked if the model tries to add them.
- **Outputs:** ATS-safe single-column DOCX and PDF (Lato, bundled in `assets/fonts`, auto-fitted to your page limit),
  plain text; side-by-side diff; change log with reasons; skill gaps.
- **Retry** with feedback (and a different model or intensity). Every version is kept, and you can mark one ⭐ final.
  A one-click "Fix flagged issues" retry is also available.
- **History tab:** one card per application showing your original resume, the JD and the tailored resume side by
  side, each downloadable (PDF/DOCX/TXT, cover letter), plus full details on demand. Searchable, ZIP export,
  **Clear all history** button, and automatic deletion after 30 days (`HISTORY_RETENTION_DAYS`, 0 = keep forever).
- **Model dropdown** populated from your API key, showing price per model; token estimate before each run;
  exact usage per call logged in the **Usage tab** (by model / day / company / pipeline step).

## Run locally
```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
Put your API keys in a `.env` file in the project folder (copy `.env.example`). Gemini, Groq and OpenAI are supported.
Any one key is enough:
```
GEMINI_API_KEY=...
GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-...
DEFAULT_PROVIDER=gemini
```
`.env` is git-ignored, so keys are never committed.

On startup the app checks each key with a tiny real request, hides models that can't do the job (e.g. a model with
a 1,000 tokens/minute output cap), and pre-selects the best working model. If a step can't finish because a provider
is out of credit, over its token limit, rate-limited or overloaded, the run automatically continues on the next
working provider, and the app tells you it switched.
History is saved to `data/redrafter.db` (SQLite).

Tests: `python -m pytest -q tests`

## Deploy on Streamlit Community Cloud (free)
1. Push this folder to a GitHub repo (`.gitignore` already excludes secrets, the venv and the database).
2. **Persistent history:** Streamlit Cloud's disk is wiped on restart, so use Supabase:
   create a free project at supabase.com → SQL editor → run `storage/supabase_schema.sql`.
3. share.streamlit.io → **New app** → pick the repo, main file `app.py`.
4. **App settings → Secrets**, paste (see `.streamlit/secrets.toml.example`):
   ```toml
   OPENAI_API_KEY = "sk-..."            # replaces .env on the cloud
   APP_USERNAME = "your-id"             # login page: only this ID + password can use the app
   APP_PASSWORD = "something-long"      # REQUIRED in practice: otherwise anyone with the URL spends your credit
   STORAGE = "supabase"
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_KEY = "your-service-role-key"
   ```

## Project layout
```
app.py                 Streamlit entry (login page, sidebar, tabs)
core/                  parser, prompts, llm_client, pipeline, verifier, ats_scorer, renderer, diffing, tokens
storage/               SQLite + Supabase stores with the same interface
ui/                    sidebar, redraft, results (shared view + retry), history, usage, settings
config/pricing.json    model prices (also editable in the Settings tab)
tests/                 offline tests (fake LLM) + app smoke test
```

## Notes
- Prices in `config/pricing.json` are approximate. Check openai.com/api/pricing and edit them in Settings.
- Scanned (image-only) PDFs can't be parsed. Paste the text instead.
- Cost per run with `gpt-4.1-mini` is typically around $0.01.
