import pandas as pd
import streamlit as st

from core.tokens import load_pricing, save_pricing


def render(store) -> None:
    st.header("Settings")

    st.subheader("💲 Model prices (USD per 1M tokens)")
    st.caption("Used for cost estimates. Providers change prices, so check their pricing pages. "
               "A row also covers dated variants (e.g. 'gpt-4o' covers 'gpt-4o-2024-08-06').")
    pricing = load_pricing()
    df = pd.DataFrame([{"model": k, "input": v["input"], "output": v["output"]} for k, v in pricing.items()])
    edited = st.data_editor(df, num_rows="dynamic", width="stretch", hide_index=True, key="pricing_editor",
                            column_config={"input": st.column_config.NumberColumn(min_value=0.0, format="$%.3f"),
                                           "output": st.column_config.NumberColumn(min_value=0.0, format="$%.3f")})
    if st.button("💾 Save prices"):
        rows = edited.dropna(subset=["model"])
        save_pricing({str(r.model).strip(): {"input": float(r.input or 0), "output": float(r.output or 0)}
                      for r in rows.itertuples() if str(r.model).strip()})
        st.success("Prices saved.")

    st.subheader("🗄️ Storage")
    st.write(f"History is stored in **{store.name}**.")
    if getattr(store, "file_columns_missing", False):
        from storage.supabase_store import FILE_COLUMNS_SQL

        st.warning("Uploaded resume files aren't being saved yet: your Supabase tables need two new columns. "
                   "Run this once in Supabase → SQL Editor, then reboot the app:")
        st.code(FILE_COLUMNS_SQL, language="sql")
    if store.name.startswith("SQLite"):
        st.caption("On Streamlit Community Cloud the local disk is wiped when the app restarts. "
                   "Configure Supabase (see README) to keep history there.")

    st.subheader("🔐 Privacy")
    st.markdown(
        "- API keys are read from `.env` locally or from the app's Secrets when deployed; they are never shown or "
        "stored in the database.\n"
        "- Resume and JD text are sent to the AI provider selected in the sidebar (Gemini, Groq or OpenAI). Each "
        "provider's API terms decide how that data is handled; free tiers may allow it to be used for training.\n"
        "- History (resumes, JDs, versions) is stored in the database above."
    )
