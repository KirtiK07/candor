import pandas as pd
import streamlit as st


def _table(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by, dropna=False).agg(
        calls=("id", "count"), input_tokens=("prompt_tokens", "sum"),
        output_tokens=("completion_tokens", "sum"), cost_usd=("cost_usd", "sum"),
    ).sort_values("cost_usd", ascending=False).reset_index()
    g["cost_usd"] = g["cost_usd"].round(4)
    return g


def render(store) -> None:
    st.header("Token usage & cost")
    st.caption("Exact token counts reported by the provider for every call. Costs use the prices in Settings, so "
               "they're estimates. Your provider's dashboard has the billed amount.")
    rows = store.usage_rows()
    if not rows:
        st.info("No API calls yet.")
        return
    df = pd.DataFrame(rows)
    df["cost_usd"] = df["cost_usd"].fillna(0)
    df["date"] = df["ts"].str[:10]
    df["company"] = df["company"].fillna("(failed run)")

    m = st.columns(4)
    m[0].metric("Total cost", f"${df['cost_usd'].sum():.4f}")
    m[1].metric("Total tokens", f"{int(df['prompt_tokens'].sum() + df['completion_tokens'].sum()):,}")
    m[2].metric("Resume versions", int(df["version_id"].nunique()))
    m[3].metric("API calls", len(df))

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("By model")
        st.dataframe(_table(df, "model"), width="stretch", hide_index=True)
        st.subheader("By pipeline step")
        st.dataframe(_table(df, "step"), width="stretch", hide_index=True)
    with c2:
        st.subheader("By day")
        st.dataframe(_table(df, "date").sort_values("date", ascending=False), width="stretch", hide_index=True)
        st.subheader("By company")
        st.dataframe(_table(df, "company"), width="stretch", hide_index=True)
    with st.expander("Raw call log"):
        st.dataframe(df.drop(columns=["date"]).sort_values("id", ascending=False), width="stretch", hide_index=True)
