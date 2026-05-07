"""
Main Streamlit application entry point for the Semantic BI Workflow.

This app presents a product-style demo for:
- domain pack loading
- semantic setup suggestions
- candidate question generation
- question scoring and promotion decisions
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
import yaml

# Make imports work when running: streamlit run app/app.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.pipeline import BIWorkflowPipeline


DOMAINS_DIR = PROJECT_ROOT / "domains"


def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def load_seed_questions(path: Path) -> List[str]:
    df = pd.read_csv(path)
    if "question" not in df.columns:
        return []
    return df["question"].dropna().astype(str).tolist()


def to_dict(obj: Any) -> Dict[str, Any]:
    """Convert Pydantic objects or dictionaries into dictionaries."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


def objects_to_df(items: List[Any]) -> pd.DataFrame:
    return pd.DataFrame([to_dict(item) for item in items])


def format_list_value(value: Any) -> str:
    """Format lists and dictionaries for compact dataframe display."""
    if isinstance(value, list):
        cleaned_items = [str(v).strip().rstrip(".") for v in value if str(v).strip()]
        return "; ".join(cleaned_items)
    if isinstance(value, dict):
        return str(value)
    return value


def clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Make dataframe cells more readable in Streamlit tables."""
    display_df = df.copy()
    for col in display_df.columns:
        display_df[col] = display_df[col].apply(format_list_value)
    return display_df


def get_domain_names() -> List[str]:
    if not DOMAINS_DIR.exists():
        return []
    return sorted([p.name for p in DOMAINS_DIR.iterdir() if p.is_dir()])


def load_domain_pack(domain_name: str):
    domain_path = DOMAINS_DIR / domain_name

    sample_path = domain_path / "sample.csv"
    metric_path = domain_path / "metric_registry.yaml"
    glossary_path = domain_path / "glossary.yaml"
    seed_path = domain_path / "seed_questions.csv"

    df = pd.read_csv(sample_path)
    metric_registry = load_yaml(metric_path)
    glossary = load_yaml(glossary_path)
    seed_questions = load_seed_questions(seed_path)

    return df, metric_registry, glossary, seed_questions


def metric_count(metric_registry: Dict[str, Any]) -> int:
    if "metrics" in metric_registry and isinstance(metric_registry["metrics"], list):
        return len(metric_registry["metrics"])
    return len(metric_registry)


def get_status_counts(promotion_df: pd.DataFrame) -> Dict[str, int]:
    if promotion_df.empty or "promotion_status" not in promotion_df.columns:
        return {"verified": 0, "review": 0, "reject": 0}

    counts = promotion_df["promotion_status"].value_counts().to_dict()
    return {
        "verified": counts.get("verified", 0),
        "review": counts.get("review", 0),
        "reject": counts.get("reject", 0),
    }


def run_pipeline(
    df: pd.DataFrame,
    metric_registry: Dict[str, Any],
    glossary: Dict[str, Any],
    seed_questions: List[str],
    max_questions: int,
) -> Dict[str, Any]:
    pipeline = BIWorkflowPipeline()
    return pipeline.run(
        df=df,
        metric_registry=metric_registry,
        glossary=glossary,
        seed_questions=seed_questions,
        max_questions=max_questions,
    )


st.set_page_config(
    page_title="Semantic BI Workflow",
    page_icon="📊",
    layout="wide",
)

st.title("Semantic BI Workflow")
st.caption(
    "A modular agentic workflow for BI semantic setup, candidate question generation, "
    "and verified-question scoring."
)

st.markdown(
    """
This prototype automates the most manual parts of natural-language BI setup:
field semantics, candidate question generation, and structured question validation.
"""
)

domain_names = get_domain_names()

if not domain_names:
    st.error("No domain packs found. Please create a folder under `domains/` first.")
    st.stop()

with st.sidebar:
    st.header("Workflow Settings")
    selected_domain = st.selectbox("Select domain pack", domain_names)
    max_questions = st.slider(
        "Max candidate questions",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
    )
    run_button = st.button("Run Pipeline", type="primary")

df, metric_registry, glossary, seed_questions = load_domain_pack(selected_domain)

if run_button:
    with st.spinner("Running semantic BI workflow..."):
        results = run_pipeline(
            df=df,
            metric_registry=metric_registry,
            glossary=glossary,
            seed_questions=seed_questions,
            max_questions=max_questions,
        )
        st.session_state["pipeline_results"] = results
        st.session_state["selected_domain"] = selected_domain

results = st.session_state.get("pipeline_results")

# Summary cards
st.markdown("### Workflow Summary")

summary_cols = st.columns(4)

summary_cols[0].metric("Dataset Rows", f"{df.shape[0]:,}")
summary_cols[1].metric("Fields", f"{df.shape[1]:,}")
summary_cols[2].metric("Defined Metrics", f"{metric_count(metric_registry):,}")
summary_cols[3].metric("Seed Questions", f"{len(seed_questions):,}")

if results:
    promotion_df_for_summary = pd.DataFrame(results["promotion_results"])
    status_counts = get_status_counts(promotion_df_for_summary)

    result_cols = st.columns(4)
    result_cols[0].metric("Generated Questions", len(results["candidate_questions"]))
    result_cols[1].metric("Verified", status_counts["verified"])
    result_cols[2].metric("Needs Review", status_counts["review"])
    result_cols[3].metric("Rejected", status_counts["reject"])
else:
    st.info("Run the pipeline from the sidebar to generate semantic setup and question validation results.")

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "1. Dataset & Registry",
        "2. Semantic Setup",
        "3. Candidate Questions",
        "4. Scoring & Promotion",
    ]
)

with tab1:
    st.subheader("Dataset & Business Context")
    st.write(f"Domain pack: `{selected_domain}`")

    st.markdown("#### Dataset Preview")
    st.dataframe(df.head(20), use_container_width=True)

    st.markdown("#### Business Context Files")

    context_cols = st.columns(3)

    with context_cols[0]:
        st.metric("Metric Registry Items", metric_count(metric_registry))

    with context_cols[1]:
        st.metric("Glossary Terms", len(glossary))

    with context_cols[2]:
        st.metric("Seed Questions", len(seed_questions))

    with st.expander("View Metric Registry"):
        st.json(metric_registry)

    with st.expander("View Glossary"):
        st.json(glossary)

    with st.expander("View Seed Questions"):
        st.dataframe(
            pd.DataFrame({"question": seed_questions}),
            use_container_width=True,
        )

with tab2:
    st.subheader("Semantic Setup Suggestions")

    st.markdown(
        """
The semantic setup layer profiles raw fields and recommends how each field should be interpreted
by a natural-language BI system.
"""
    )

    if not results:
        st.info("Run the pipeline from the sidebar to generate semantic setup suggestions.")
    else:
        field_profiles_df = clean_dataframe_for_display(objects_to_df(results["field_profiles"]))
        field_suggestions_df = clean_dataframe_for_display(objects_to_df(results["field_suggestions"]))

        profile_cols = [
            col for col in [
                "field_name",
                "dtype",
                "null_rate",
                "distinct_count",
                "heuristic_role",
                "sample_values",
            ]
            if col in field_profiles_df.columns
        ]

        suggestion_cols = [
            col for col in [
                "field_name",
                "include",
                "friendly_name",
                "field_role",
                "default_aggregation",
                "format",
                "synonyms",
                "confidence",
                "rationale",
            ]
            if col in field_suggestions_df.columns
        ]

        st.markdown("#### Field Profiles")
        st.dataframe(
            field_profiles_df[profile_cols],
            use_container_width=True,
        )

        st.markdown("#### Semantic Field Suggestions")
        st.dataframe(
            field_suggestions_df[suggestion_cols],
            use_container_width=True,
        )

        csv = field_suggestions_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Field Suggestions CSV",
            data=csv,
            file_name="field_suggestions.csv",
            mime="text/csv",
        )

with tab3:
    st.subheader("Candidate Questions")

    st.markdown(
        """
Candidate questions are generated from the semantic layer, metric definitions,
glossary terms, and seed question patterns.
"""
    )

    if not results:
        st.info("Run the pipeline from the sidebar to generate candidate questions.")
    else:
        candidate_df = clean_dataframe_for_display(objects_to_df(results["candidate_questions"]))

        candidate_cols = [
            col for col in [
                "question_text",
                "target_metrics",
                "target_dimensions",
                "filters",
                "time_grain",
            ]
            if col in candidate_df.columns
        ]

        st.dataframe(
            candidate_df[candidate_cols],
            use_container_width=True,
        )

        csv = candidate_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Candidate Questions CSV",
            data=csv,
            file_name="candidate_questions.csv",
            mime="text/csv",
        )

with tab4:
    st.subheader("Question Scoring & Promotion")

    st.markdown(
        """
Each candidate question is scored across grounding, business relevance, clarity,
analytical richness, and usability before being promoted to verified, review, or reject.
"""
    )

    if not results:
        st.info("Run the pipeline from the sidebar to generate scoring results.")
    else:
        promotion_df = pd.DataFrame(results["promotion_results"])

        status_counts = get_status_counts(promotion_df)

        metric_cols = st.columns(4)
        metric_cols[0].metric("Verified", status_counts["verified"])
        metric_cols[1].metric("Review", status_counts["review"])
        metric_cols[2].metric("Reject", status_counts["reject"])

        if not promotion_df.empty and "final_score" in promotion_df.columns:
            metric_cols[3].metric("Average Score", round(promotion_df["final_score"].mean(), 1))
        else:
            metric_cols[3].metric("Average Score", "N/A")

        status_options = sorted(promotion_df["promotion_status"].unique())

        status_filter = st.multiselect(
            "Filter by promotion status",
            options=status_options,
            default=status_options,
        )

        filtered_df = promotion_df[promotion_df["promotion_status"].isin(status_filter)].copy()

        status_order = {
            "verified": 0,
            "review": 1,
            "reject": 2,
        }

        filtered_df["status_order"] = filtered_df["promotion_status"].map(status_order).fillna(99)
        filtered_df = filtered_df.sort_values(
            by=["status_order", "final_score"],
            ascending=[True, False],
        )

        display_cols = [
            col for col in [
                "promotion_status",
                "final_score",
                "question_text",
                "promotion_reason",
                "deal_breakers",
                "easy_to_fix_items",
                "ambiguity_flags",
            ]
            if col in filtered_df.columns
        ]

        st.markdown("#### Promotion Summary")
        st.dataframe(
            clean_dataframe_for_display(filtered_df[display_cols]),
            use_container_width=True,
        )

        st.markdown("#### Status Counts")
        status_counts_df = (
            promotion_df["promotion_status"]
            .value_counts()
            .reset_index()
        )
        status_counts_df.columns = ["promotion_status", "count"]
        st.dataframe(status_counts_df, use_container_width=True)

        csv = promotion_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Promotion Results CSV",
            data=csv,
            file_name="promotion_results.csv",
            mime="text/csv",
        )