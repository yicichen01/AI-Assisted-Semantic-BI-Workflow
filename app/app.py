"""
Main Streamlit application entry point for the AI-Assisted Semantic BI Workflow.

This app presents a product-style demo for:
- domain pack loading
- semantic setup suggestions
- candidate question generation
- question scoring and promotion decisions
- verified-question review workflow
- future BI readiness dashboard and audit loop
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
import yaml

# Make imports work when running: streamlit run app/app.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.pipeline import BIWorkflowPipeline
from services.llm_service import GeminiLLMService


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


def request_scroll_to_top():
    """Mark that the app should scroll to top after the next rerun renders."""
    st.session_state["should_scroll_to_top"] = True


def scroll_to_top():
    """Force Streamlit main page to scroll to top after sidebar navigation changes."""
    components.html(
        """
        <script>
            function forceScrollTop() {
                const parentDoc = window.parent.document;

                try {
                    window.parent.scrollTo(0, 0);
                } catch (e) {}

                const explicitSelectors = [
                    "html",
                    "body",
                    "section.main",
                    ".main",
                    "div[data-testid='stAppViewContainer']",
                    "div[data-testid='stMain']",
                    "div[data-testid='stMainBlockContainer']",
                    "div[data-testid='block-container']",
                    "div[data-testid='stVerticalBlock']"
                ];

                explicitSelectors.forEach((selector) => {
                    const el = parentDoc.querySelector(selector);
                    if (el) {
                        try {
                            el.scrollTop = 0;
                            el.scrollTo({ top: 0, left: 0, behavior: "auto" });
                        } catch (e) {}
                    }
                });

                const allElements = parentDoc.querySelectorAll("*");
                allElements.forEach((el) => {
                    try {
                        if (el.scrollHeight > el.clientHeight) {
                            el.scrollTop = 0;
                        }
                    } catch (e) {}
                });
            }

            forceScrollTop();
            window.parent.requestAnimationFrame(forceScrollTop);
            setTimeout(forceScrollTop, 50);
            setTimeout(forceScrollTop, 150);
            setTimeout(forceScrollTop, 350);
            setTimeout(forceScrollTop, 700);
            setTimeout(forceScrollTop, 1200);
        </script>
        """,
        height=0,
    )


def get_domain_names() -> List[str]:
    if not DOMAINS_DIR.exists():
        return []
    return sorted([p.name for p in DOMAINS_DIR.iterdir() if p.is_dir()])


def format_domain_label(domain_name: str) -> str:
    """Convert folder-style domain names into readable UI labels."""
    return domain_name.replace("_", " ").title()


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
    llm_service: Optional[Any] = None,
    domain_name: str = "",
) -> Dict[str, Any]:
    pipeline = BIWorkflowPipeline()
    return pipeline.run(
        df=df,
        metric_registry=metric_registry,
        glossary=glossary,
        seed_questions=seed_questions,
        max_questions=max_questions,
        llm_service=llm_service,
        domain_name=domain_name,
    )


def get_results_for_current_domain(selected_domain: str):
    """Avoid showing stale results after switching domains."""
    if st.session_state.get("selected_domain") != selected_domain:
        return None
    return st.session_state.get("pipeline_results")


def get_promotion_df(results: Optional[Dict[str, Any]]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results.get("promotion_results", []))


def render_product_header(
    df: pd.DataFrame,
    metric_registry: Dict[str, Any],
    glossary: Dict[str, Any],
    seed_questions: List[str],
    results: Optional[Dict[str, Any]],
):
    """Render the top product-style overview section."""
    st.title("AI-Assisted BI Semantic Workflow")
    st.subheader("Configurable semantic setup and question validation for BI teams")

    st.markdown(
        """
        This MVP helps BI teams turn operational datasets into governed semantic metadata,
        validated BI questions, verified question libraries, and semantic quality monitoring.
        """
    )

    st.markdown("### What this app does")

    value_cols = st.columns(3)

    with value_cols[0]:
        st.markdown(
            """
            **Semantic Setup**  
            Profiles raw fields and recommends BI-ready metadata, synonyms, and review notes.
            """
        )

    with value_cols[1]:
        st.markdown(
            """
            **Question Validation**  
            Scores candidate BI questions across grounding, clarity, relevance, and usability.
            """
        )

    with value_cols[2]:
        st.markdown(
            """
            **Governed Promotion**  
            Separates questions into `Verified`, `Review`, or `Reject` before business use.
            """
        )

    st.markdown("### Workflow")

    st.markdown(
        """
        ```text
        Operational Dataset
                ↓
        Field Profiling
                ↓
        Semantic Metadata Agent
                ↓
        Question Validation + Guardrails
                ↓
        Verified Question Library
                ↓
        BI Dashboard + Monitoring
        ```
        """
    )

    st.markdown("### Try the Demo in 3 Steps")

    st.markdown(
        """
        **Step 1:** Select a curated demo domain pack or preview an uploaded CSV  
        **Step 2:** Run the workflow to generate semantic metadata and candidate questions  
        **Step 3:** Review validation results, verified questions, and semantic quality signals
        """
    )

    st.markdown("### Selected Domain Snapshot")

    snapshot_cols = st.columns(4)
    snapshot_cols[0].metric("Dataset Rows", f"{df.shape[0]:,}")
    snapshot_cols[1].metric("Fields", f"{df.shape[1]:,}")
    snapshot_cols[2].metric("Defined Metrics", f"{metric_count(metric_registry):,}")
    snapshot_cols[3].metric("Seed Questions", f"{len(seed_questions):,}")

    if results:
        promotion_df = get_promotion_df(results)
        status_counts = get_status_counts(promotion_df)

        st.markdown("### Latest Validation Outcome")

        outcome_cols = st.columns(4)
        outcome_cols[0].metric("Verified", status_counts["verified"])
        outcome_cols[1].metric("Needs Review", status_counts["review"])
        outcome_cols[2].metric("Rejected", status_counts["reject"])

        if not promotion_df.empty and "final_score" in promotion_df.columns:
            outcome_cols[3].metric("Average Score", round(promotion_df["final_score"].mean(), 1))
        else:
            outcome_cols[3].metric("Average Score", "N/A")


def render_pipeline_status(results: Optional[Dict[str, Any]]):
    if results:
        st.success("Pipeline results are available for the selected domain.")
    else:
        st.info("Run the pipeline from the sidebar to generate semantic setup and question validation results.")


def render_business_context(
    selected_domain: str,
    df: pd.DataFrame,
    metric_registry: Dict[str, Any],
    glossary: Dict[str, Any],
    seed_questions: List[str],
    results: Optional[Dict[str, Any]],
):
    st.header("1. Business Context")
    st.write(f"Current domain pack: `{selected_domain}`")

    st.markdown(
        """
        This app uses lightweight domain packs to simulate how a BI team can manage
        dataset context, approved metric definitions, glossary terms, and seed questions
        across different business areas.
        """
    )

    context_cols = st.columns(4)
    context_cols[0].metric("Dataset Rows", f"{df.shape[0]:,}")
    context_cols[1].metric("Dataset Fields", f"{df.shape[1]:,}")
    context_cols[2].metric("Defined Metrics", f"{metric_count(metric_registry):,}")
    context_cols[3].metric("Seed Questions", f"{len(seed_questions):,}")

    if results:
        promotion_df = get_promotion_df(results)
        status_counts = get_status_counts(promotion_df)

        st.markdown("#### Latest Pipeline Outcome")
        outcome_cols = st.columns(4)
        outcome_cols[0].metric("Generated Questions", len(results.get("candidate_questions", [])))
        outcome_cols[1].metric("Verified", status_counts["verified"])
        outcome_cols[2].metric("Needs Review", status_counts["review"])
        outcome_cols[3].metric("Rejected", status_counts["reject"])

    st.markdown("#### Domain Pack Contents")
    st.markdown(
        """
        Each domain pack contains:

        - `sample.csv`: sample operational dataset
        - `metric_registry.yaml`: approved metric definitions and business owners
        - `glossary.yaml`: sample business terms and synonyms
        - `seed_questions.csv`: starter questions for candidate generation and validation
        """
    )


def render_upload_select_dataset(
    selected_domain: str,
    df: pd.DataFrame,
    metric_registry: Dict[str, Any],
    glossary: Dict[str, Any],
    seed_questions: List[str],
):
    st.header("2. Upload / Select Dataset")
    st.write(f"Selected domain pack: `{format_domain_label(selected_domain)}`")

    st.markdown(
        """
        The current public demo uses curated domain packs for the full workflow.
        CSV upload is available for field preview only because full semantic validation
        requires a metric registry, glossary, and seed questions.
        """
    )

    uploaded_file = st.file_uploader(
        "Optional: Upload a CSV for field preview",
        type=["csv"],
        help=(
            "The full workflow currently uses curated domain packs. "
            "Uploaded CSVs are used for preview only."
        ),
        key=f"dataset_preview_csv_uploader_{selected_domain}",
    )

    if uploaded_file is not None:
        try:
            uploaded_df = pd.read_csv(uploaded_file)

            st.markdown("#### Uploaded CSV Preview")
            st.dataframe(uploaded_df.head(20), use_container_width=True)

            upload_cols = st.columns(3)
            upload_cols[0].metric("Uploaded Rows", f"{uploaded_df.shape[0]:,}")
            upload_cols[1].metric("Uploaded Fields", f"{uploaded_df.shape[1]:,}")
            upload_cols[2].metric("Missing Cells", f"{uploaded_df.isna().sum().sum():,}")

            st.info(
                "This uploaded file is shown for preview only. The full semantic workflow "
                "still uses the selected domain pack because validation requires a metric "
                "registry, glossary, and seed questions."
            )

        except Exception as exc:
            st.error(f"Unable to read uploaded CSV: {exc}")

    st.markdown("#### Selected Domain Dataset Preview")
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


def render_field_profiling(results: Optional[Dict[str, Any]]):
    st.header("3. Field Profiling")

    st.markdown(
        """
        The field profiling layer inspects raw columns and identifies data types,
        null rates, distinct counts, sample values, and heuristic BI roles.
        """
    )

    if not results:
        st.info("Run the pipeline from the sidebar to generate field profiles.")
        return

    field_profiles_df = clean_dataframe_for_display(objects_to_df(results["field_profiles"]))

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

    st.markdown("#### Field Profiles")
    st.dataframe(
        field_profiles_df[profile_cols],
        use_container_width=True,
    )


def render_semantic_metadata_agent(results: Optional[Dict[str, Any]]):
    st.header("4. Semantic Metadata Agent")

    st.markdown(
        """
        The semantic metadata layer recommends how each field should be interpreted by a
        natural-language BI system. In the upgraded design, this section will support
        optional Gemini-assisted generation with rule-based fallback.
        """
    )

    # --- Mode toggle ---
    mode = st.radio(
        "Metadata generation mode",
        options=["Rule-based", "LLM-assisted (Gemini)"],
        index=0,
        horizontal=True,
        key="semantic_mode_toggle",
        help=(
            "Rule-based uses heuristics only. "
            "LLM-assisted calls Gemini to enrich field metadata; "
            "falls back to rule-based if the API key is missing or the call fails."
        ),
    )
    st.session_state["semantic_mode"] = mode

    # Show a small status note for LLM mode without exposing the key
    if mode == "LLM-assisted (Gemini)":
        llm_service: GeminiLLMService = st.session_state.get("llm_service")
        if llm_service is None:
            llm_service = GeminiLLMService.from_env()
            st.session_state["llm_service"] = llm_service

        if llm_service.is_available():
            st.success("Gemini API key detected. LLM-assisted mode is active.", icon="✅")
        else:
            st.info(
                "No Gemini API key found. Add GEMINI_API_KEY to `.streamlit/secrets.toml` "
                "or set it as an environment variable. Rule-based output will be used.",
                icon="ℹ️",
            )

    if not results:
        st.info("Run the pipeline from the sidebar to generate semantic setup suggestions.")
        return

    # Show which mode produced the current results
    produced_by = st.session_state.get("last_run_mode", "Rule-based")
    st.caption(f"Results produced by: **{produced_by}**")

    field_suggestions_df = clean_dataframe_for_display(objects_to_df(results["field_suggestions"]))

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


def render_question_validation(results: Optional[Dict[str, Any]]):
    st.header("5. Question Validation")

    st.markdown(
        """
        Candidate BI questions are generated from domain context, metric definitions,
        glossary terms, and seed question patterns. They are then scored across
        grounding, relevance, clarity, analytical richness, and usability.
        """
    )

    if not results:
        st.info("Run the pipeline from the sidebar to generate candidate questions and scoring results.")
        return

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

    st.markdown("#### Candidate Questions")
    st.dataframe(
        candidate_df[candidate_cols],
        use_container_width=True,
    )

    promotion_df = pd.DataFrame(results["promotion_results"])
    status_counts = get_status_counts(promotion_df)

    st.markdown("#### Validation Summary")
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

    csv = promotion_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Promotion Results CSV",
        data=csv,
        file_name="promotion_results.csv",
        mime="text/csv",
    )


def render_verified_question_library(results: Optional[Dict[str, Any]]):
    st.header("6. Verified Question Library")

    st.markdown(
        """
        The verified question library is the trusted output layer. It separates questions
        that are ready for business use from questions that need review or rejection.
        """
    )

    if not results:
        st.info("Run the pipeline from the sidebar to generate verified question candidates.")
        return

    promotion_df = pd.DataFrame(results["promotion_results"])

    if promotion_df.empty or "promotion_status" not in promotion_df.columns:
        st.warning("No promotion results are available.")
        return

    verified_df = promotion_df[promotion_df["promotion_status"] == "verified"].copy()

    if verified_df.empty:
        st.warning("No verified questions were promoted in the latest run.")
        return

    display_cols = [
        col for col in [
            "promotion_status",
            "final_score",
            "question_text",
            "promotion_reason",
            "easy_to_fix_items",
            "ambiguity_flags",
        ]
        if col in verified_df.columns
    ]

    st.metric("Verified Questions", len(verified_df))
    st.dataframe(
        clean_dataframe_for_display(verified_df[display_cols]),
        use_container_width=True,
    )

    csv = verified_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Verified Questions CSV",
        data=csv,
        file_name="verified_questions.csv",
        mime="text/csv",
    )


def render_analytics_dashboard(results: Optional[Dict[str, Any]]):
    st.header("7. Analytics Dashboard")

    st.markdown(
        """
        This dashboard summarizes semantic quality, validation outcomes, and questions
        that need review before they can be trusted for self-service BI.
        """
    )

    if not results:
        st.info("Run the pipeline from the sidebar to populate dashboard signals.")
        return

    promotion_df = pd.DataFrame(results["promotion_results"])

    if promotion_df.empty:
        st.warning("No promotion results are available.")
        return

    status_counts = get_status_counts(promotion_df)

    # Softer, dashboard-friendly palette
    status_color_map = {
        "verified": "#3BB273",  # soft green
        "review": "#F2B84B",    # soft amber
        "reject": "#E75A5A",    # soft red
    }

    amazon_orange = "#FF9900"
    amazon_dark = "#232F3E"
    soft_gray = "#EAECEF"
    soft_gray_bar = "#9FA6B2"

    chart_font = dict(
        size=16,
        color=amazon_dark,
    )

    axis_font = dict(
        size=16,
        color=amazon_dark,
    )

    tick_font = dict(
        size=15,
        color="#5F6B7A",
    )

    # -----------------------------
    # KPI cards
    # -----------------------------
    st.markdown("#### Semantic Validation Summary")

    metric_cols = st.columns(4)
    metric_cols[0].metric("Verified", status_counts["verified"])
    metric_cols[1].metric("Needs Review", status_counts["review"])
    metric_cols[2].metric("Rejected", status_counts["reject"])

    if "final_score" in promotion_df.columns:
        metric_cols[3].metric("Average Score", round(promotion_df["final_score"].mean(), 1))
    else:
        metric_cols[3].metric("Average Score", "N/A")

    # -----------------------------
    # Validation Status Distribution
    # -----------------------------
    st.markdown("#### Validation Status Distribution")

    status_counts_df = (
        promotion_df["promotion_status"]
        .value_counts()
        .reset_index()
    )
    status_counts_df.columns = ["promotion_status", "count"]

    status_order = ["verified", "review", "reject"]
    status_counts_df["status_order"] = status_counts_df["promotion_status"].apply(
        lambda x: status_order.index(x) if x in status_order else 99
    )
    status_counts_df = status_counts_df.sort_values("status_order")

    fig_status = px.pie(
        status_counts_df,
        names="promotion_status",
        values="count",
        color="promotion_status",
        color_discrete_map=status_color_map,
        hole=0.45,
    )

    fig_status.update_traces(
        textposition="inside",
        textinfo="percent+label",
        textfont_size=16,
        marker=dict(line=dict(color="white", width=2)),
        hovertemplate="<b>%{label}</b><br>Questions: %{value}<br>Share: %{percent}<extra></extra>",
    )

    fig_status.update_layout(
        height=360,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
            font=dict(size=15, color=amazon_dark),
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=20, r=20, t=20, b=70),
        font=chart_font,
    )

    st.plotly_chart(fig_status, use_container_width=True)

    # -----------------------------
    # Score Spread by Status
    # -----------------------------
    if "final_score" in promotion_df.columns:
        st.markdown("#### Score Spread by Status")

        fig_box = px.box(
            promotion_df,
            x="promotion_status",
            y="final_score",
            color="promotion_status",
            points="all",
            color_discrete_map=status_color_map,
            category_orders={"promotion_status": status_order},
            labels={
                "promotion_status": "Promotion Status",
                "final_score": "Final Score",
            },
        )

        fig_box.update_traces(
            marker=dict(size=8, opacity=0.65),
            line=dict(width=2),
        )

        fig_box.update_layout(
            height=380,
            showlegend=False,
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=20, r=20, t=20, b=50),
            xaxis=dict(
                title=dict(text="Promotion Status", font=axis_font),
                tickfont=tick_font,
                tickangle=0,
            ),
            yaxis=dict(
                range=[0, 100],
                showgrid=True,
                gridcolor=soft_gray,
                zeroline=False,
                title=dict(text="Final Score", font=axis_font),
                tickfont=tick_font,
            ),
            font=chart_font,
        )

        st.plotly_chart(fig_box, use_container_width=True)

    # -----------------------------
    # Only show score dimension chart if there are real dimensions
    # -----------------------------
    score_cols = [
        col for col in [
            "grounding_score",
            "relevance_score",
            "clarity_score",
            "analytical_richness_score",
            "usability_score",
        ]
        if col in promotion_df.columns
    ]

    if len(score_cols) >= 2:
        st.markdown("#### Average Score by Validation Dimension")

        score_summary = (
            promotion_df[score_cols]
            .mean()
            .reset_index()
        )
        score_summary.columns = ["score_dimension", "average_score"]

        score_summary["score_dimension"] = (
            score_summary["score_dimension"]
            .str.replace("_", " ")
            .str.title()
        )

        fig_scores = px.bar(
            score_summary,
            x="average_score",
            y="score_dimension",
            orientation="h",
            text=score_summary["average_score"].round(1),
            color_discrete_sequence=[amazon_orange],
            labels={
                "average_score": "Average Score",
                "score_dimension": "Score Dimension",
            },
        )

        fig_scores.update_traces(
            textposition="outside",
            marker_line_width=0,
        )

        fig_scores.update_layout(
            height=360,
            showlegend=False,
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=20, r=70, t=20, b=40),
            xaxis=dict(
                range=[0, 100],
                showgrid=True,
                gridcolor=soft_gray,
                zeroline=False,
                title=dict(text="Average Score", font=axis_font),
                tickfont=tick_font,
            ),
            yaxis=dict(
                title=None,
                tickangle=0,
                tickfont=tick_font,
            ),
            font=chart_font,
        )

        st.plotly_chart(fig_scores, use_container_width=True)

    # -----------------------------
    # Guardrail / Review Issue Breakdown
    # -----------------------------
    st.markdown("#### Guardrail and Review Issue Breakdown")

    def count_issue_items(value: Any) -> int:
        if value is None:
            return 0

        if isinstance(value, list):
            return len([item for item in value if str(item).strip()])

        if isinstance(value, dict):
            return len(value)

        text = str(value).strip()
        if not text or text.lower() in ["nan", "none", "[]", "{}"]:
            return 0

        if ";" in text:
            return len([item for item in text.split(";") if item.strip()])

        return 1

    def has_issue(value: Any) -> bool:
        return count_issue_items(value) > 0

    issue_columns = [
        col for col in [
            "deal_breakers",
            "easy_to_fix_items",
            "ambiguity_flags",
        ]
        if col in promotion_df.columns
    ]

    if issue_columns:
        issue_summary = []

        for col in issue_columns:
            issue_summary.append(
                {
                    "issue_type": col.replace("_", " ").title(),
                    "issue_count": int(promotion_df[col].apply(count_issue_items).sum()),
                }
            )

        issue_summary_df = pd.DataFrame(issue_summary)

        fig_issues = px.bar(
            issue_summary_df,
            x="issue_count",
            y="issue_type",
            orientation="h",
            text="issue_count",
            color_discrete_sequence=[soft_gray_bar],
            labels={
                "issue_count": "Number of Issues",
                "issue_type": "Issue Type",
            },
        )

        fig_issues.update_traces(
            textposition="outside",
            marker_line_width=0,
        )

        fig_issues.update_layout(
            height=300,
            showlegend=False,
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=20, r=70, t=20, b=40),
            xaxis=dict(
                showgrid=True,
                gridcolor=soft_gray,
                zeroline=False,
                title=dict(text="Number of Issues", font=axis_font),
                tickfont=tick_font,
            ),
            yaxis=dict(
                title=None,
                tickangle=0,
                tickfont=tick_font,
            ),
            font=chart_font,
        )

        st.plotly_chart(fig_issues, use_container_width=True)
    else:
        st.info("No detailed guardrail issue columns are available in the current pipeline output.")

    # -----------------------------
    # Attention Buckets
    # -----------------------------
    st.markdown("#### Questions Requiring Attention")

    st.markdown(
        """
        Questions are separated into review buckets based on the type of issue detected.
        **Deal-breaker issues are treated as the highest-priority bucket.** If a question has
        both deal-breaker and easy-to-fix items, it is counted under deal-breakers because
        blocking issues must be resolved before smaller wording or clarity improvements matter.
        """
    )

    attention_df = promotion_df[
        promotion_df["promotion_status"].isin(["review", "reject"])
    ].copy()

    if attention_df.empty:
        st.success("No review or reject items in the latest run.")
        return

    for col in ["deal_breakers", "easy_to_fix_items", "ambiguity_flags"]:
        if col not in attention_df.columns:
            attention_df[col] = None

    attention_df["has_deal_breaker"] = attention_df["deal_breakers"].apply(has_issue)
    attention_df["has_easy_to_fix"] = attention_df["easy_to_fix_items"].apply(has_issue)
    attention_df["has_ambiguity"] = attention_df["ambiguity_flags"].apply(has_issue)

    deal_breaker_df = attention_df[attention_df["has_deal_breaker"]].copy()

    easy_to_fix_df = attention_df[
        (~attention_df["has_deal_breaker"])
        & (
            attention_df["has_easy_to_fix"]
            | attention_df["has_ambiguity"]
            | attention_df["promotion_status"].eq("review")
        )
    ].copy()

    unclassified_attention_df = attention_df[
        (~attention_df["has_deal_breaker"])
        & (~attention_df.index.isin(easy_to_fix_df.index))
    ].copy()

    attention_cols = [
        col for col in [
            "promotion_status",
            "final_score",
            "question_text",
            "promotion_reason",
            "deal_breakers",
            "easy_to_fix_items",
            "ambiguity_flags",
        ]
        if col in attention_df.columns
    ]

    st.markdown("##### Deal-Breaker Questions")
    st.caption(
        "These questions have blocking issues such as unsupported metrics, missing fields, "
        "or context that is not grounded enough to promote."
    )

    if deal_breaker_df.empty:
        st.success("No deal-breaker questions in the latest run.")
    else:
        deal_breaker_df = deal_breaker_df.sort_values(
            by="final_score" if "final_score" in deal_breaker_df.columns else "promotion_status",
            ascending=True,
        )

        st.dataframe(
            clean_dataframe_for_display(deal_breaker_df[attention_cols]),
            use_container_width=True,
        )

    st.markdown("##### Easy-to-Fix Review Questions")
    st.caption(
        "These questions do not have deal-breaker issues, but they may need clearer wording, "
        "a better grain, a more specific time window, or a human review note."
    )

    if easy_to_fix_df.empty:
        st.success("No easy-to-fix review questions in the latest run.")
    else:
        easy_to_fix_df = easy_to_fix_df.sort_values(
            by="final_score" if "final_score" in easy_to_fix_df.columns else "promotion_status",
            ascending=True,
        )

        st.dataframe(
            clean_dataframe_for_display(easy_to_fix_df[attention_cols]),
            use_container_width=True,
        )

    if not unclassified_attention_df.empty:
        st.markdown("##### Other Review Items")
        st.caption(
            "These questions were marked for attention, but the current pipeline output does "
            "not include a detailed issue category."
        )

        st.dataframe(
            clean_dataframe_for_display(unclassified_attention_df[attention_cols]),
            use_container_width=True,
        )


def render_monitoring_audit_log(results: Optional[Dict[str, Any]]):
    st.header("8. Monitoring & Audit Log")

    st.markdown(
        """
        This section previews the future audit and feedback loop. The current version shows
        the latest in-session review trail. Phase 5 will add SQLite-backed persistence for
        semantic metadata, question scores, verified questions, and audit events.
        """
    )

    if not results:
        st.info("Run the pipeline from the sidebar to generate review activity.")
        return

    promotion_df = pd.DataFrame(results["promotion_results"])

    if promotion_df.empty:
        st.warning("No review activity is available.")
        return

    st.markdown("#### Latest Review Trail Preview")

    audit_cols = [
        col for col in [
            "promotion_status",
            "final_score",
            "question_text",
            "promotion_reason",
            "deal_breakers",
            "easy_to_fix_items",
            "ambiguity_flags",
        ]
        if col in promotion_df.columns
    ]

    st.dataframe(
        clean_dataframe_for_display(promotion_df[audit_cols]),
        use_container_width=True,
    )

    st.markdown("#### Planned Audit Events")
    st.markdown(
        """
        Future audit events will include:

        - Metadata generation
        - Question approval
        - Question rejection
        - Question promotion
        - Reviewer feedback notes
        - Role-based user actions
        """
    )


st.set_page_config(
    page_title="AI-Assisted BI Semantic Workflow",
    page_icon="📊",
    layout="wide",
)

domain_names = get_domain_names()

if not domain_names:
    st.error("No domain packs found. Please create a folder under `domains/` first.")
    st.stop()

with st.sidebar:
    st.header("Workflow Settings")

    selected_domain = st.selectbox(
        "Select domain pack",
        domain_names,
        format_func=format_domain_label,
        key="domain_selector",
        on_change=request_scroll_to_top,
    )

    max_questions = st.slider(
        "Max candidate questions",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
    )

    run_button = st.button("Run Pipeline", type="primary")

    st.divider()

    page = st.radio(
        "Workflow Navigation",
        [
            "1. Business Context",
            "2. Upload / Select Dataset",
            "3. Field Profiling",
            "4. Semantic Metadata Agent",
            "5. Question Validation",
            "6. Verified Question Library",
            "7. Analytics Dashboard",
            "8. Monitoring & Audit Log",
        ],
        key="workflow_navigation_page",
        on_change=request_scroll_to_top,
    )

    st.divider()
    st.caption("Current version: domain packs + rule-based semantic workflow")
    st.caption("Next upgrades: Gemini API, role simulator, SQLite, audit loop")

df, metric_registry, glossary, seed_questions = load_domain_pack(selected_domain)

if st.session_state.get("selected_domain") != selected_domain:
    st.session_state.pop("pipeline_results", None)

if run_button:
    with st.spinner("Running semantic BI workflow..."):
        # Resolve LLM service based on current mode selection
        selected_mode = st.session_state.get("semantic_mode", "Rule-based")
        active_llm_service = None
        if selected_mode == "LLM-assisted (Gemini)":
            active_llm_service = st.session_state.get("llm_service")
            if active_llm_service is None:
                active_llm_service = GeminiLLMService.from_env()
                st.session_state["llm_service"] = active_llm_service

        results = run_pipeline(
            df=df,
            metric_registry=metric_registry,
            glossary=glossary,
            seed_questions=seed_questions,
            max_questions=max_questions,
            llm_service=active_llm_service,
            domain_name=selected_domain,
        )
        st.session_state["pipeline_results"] = results
        st.session_state["selected_domain"] = selected_domain
        st.session_state["last_run_mode"] = selected_mode

results = get_results_for_current_domain(selected_domain)

if page != "1. Business Context":
    st.caption(f"Selected domain pack: {format_domain_label(selected_domain)}")
    render_pipeline_status(results)
    st.divider()

if page == "1. Business Context":
    render_product_header(
        df=df,
        metric_registry=metric_registry,
        glossary=glossary,
        seed_questions=seed_questions,
        results=results,
    )

    render_pipeline_status(results)

    st.divider()

    render_business_context(
        selected_domain=selected_domain,
        df=df,
        metric_registry=metric_registry,
        glossary=glossary,
        seed_questions=seed_questions,
        results=results,
    )

elif page == "2. Upload / Select Dataset":
    render_upload_select_dataset(
        selected_domain=selected_domain,
        df=df,
        metric_registry=metric_registry,
        glossary=glossary,
        seed_questions=seed_questions,
    )

elif page == "3. Field Profiling":
    render_field_profiling(results)

elif page == "4. Semantic Metadata Agent":
    render_semantic_metadata_agent(results)

elif page == "5. Question Validation":
    render_question_validation(results)

elif page == "6. Verified Question Library":
    render_verified_question_library(results)

elif page == "7. Analytics Dashboard":
    render_analytics_dashboard(results)

elif page == "8. Monitoring & Audit Log":
    render_monitoring_audit_log(results)

# Run the scroll script after all content is rendered.
# This is more reliable than calling it before page content is mounted.
if st.session_state.pop("should_scroll_to_top", False):
    scroll_to_top()