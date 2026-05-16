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


ISSUE_TEXT_COLUMNS = {
    "deal_breakers",
    "easy_to_fix_items",
    "ambiguity_flags",
}


def ensure_display_sentence(text: Any) -> str:
    """Format issue-style display text as a readable sentence."""
    cleaned = str(text).strip()

    if not cleaned or cleaned.lower() in ["nan", "none", "[]", "{}"]:
        return ""

    cleaned = cleaned.rstrip(".")

    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    return f"{cleaned}."


def format_list_value(value: Any) -> str:
    """Format issue columns as readable sentences."""
    if isinstance(value, list):
        cleaned_items = [
            ensure_display_sentence(v)
            for v in value
            if str(v).strip()
        ]
        return "; ".join(item for item in cleaned_items if item)

    if isinstance(value, dict):
        return str(value)

    return ensure_display_sentence(value)


def format_compact_list_value(value: Any) -> str:
    """Format non-sentence list columns without adding periods."""
    if isinstance(value, list):
        return "; ".join(str(v).strip() for v in value if str(v).strip())

    if isinstance(value, dict):
        return str(value)

    if value is None:
        return ""

    return value


def format_plain_value(value: Any) -> Any:
    """Leave normal scalar display values unchanged."""
    if value is None:
        return ""

    return value


def clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Make dataframe cells more readable in Streamlit tables."""
    display_df = df.copy()

    for col in display_df.columns:
        if col in ISSUE_TEXT_COLUMNS:
            display_df[col] = display_df[col].apply(format_list_value)
        elif col in ["target_metrics", "target_dimensions", "synonyms", "sample_values"]:
            display_df[col] = display_df[col].apply(format_compact_list_value)
        else:
            display_df[col] = display_df[col].apply(format_plain_value)

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


# ---------------------------------------------------------------------------
# Role simulator helpers
# ---------------------------------------------------------------------------
# This is a lightweight demo role simulator - no authentication is required.
# Roles are selected freely from the sidebar to show how different personas
# would experience the workflow in a real deployment.
#
# OIDC scaffold (disabled - for future deployment only):
# To enable real authentication, set ENABLE_OIDC = True and configure the
# provider details below. This requires streamlit-oidc or a similar library.
#
# ENABLE_OIDC = False
# OIDC_CONFIG = {
#     "provider_url": "https://your-idp.example.com",
#     "client_id": "your-client-id",
#     "redirect_uri": "https://your-app.example.com/callback",
#     "scopes": ["openid", "profile", "email"],
# }
# When ENABLE_OIDC is True, replace get_current_role() with a function that
# reads the authenticated user's role claim from the OIDC token instead of
# reading from st.session_state["demo_role"].

_ROLES = ["Admin", "BI Developer", "Business Viewer"]

_ROLE_DESCRIPTIONS = {
    "Admin": (
        "Governance access. Can run the pipeline, upload CSVs, use LLM-assisted mode, "
        "download outputs, view all pages, and use the Admin Review & Fix Simulator "
        "for review workflows."
    ),
    "BI Developer": (
        "Builder access. Can run the pipeline, upload CSVs, use LLM-assisted mode, "
        "download outputs, and view all pages. Admin review controls are hidden."
    ),
    "Business Viewer": (
        "Read-only access. Can view Business Context, Verified Question Library, "
        "Analytics Dashboard, and Monitoring & Audit Log. "
        "Cannot run the pipeline, upload data, use LLM mode, download outputs, "
        "or use review controls."
    ),
}

_VIEWER_PAGES = {
    "1. Business Context",
    "6. Verified Question Library",
    "7. Analytics Dashboard",
    "8. Monitoring & Audit Log",
}


def get_current_role() -> str:
    """Return the currently selected demo role."""
    return st.session_state.get("demo_role", "Admin")


def can_run_pipeline(role: str) -> bool:
    return role in ("Admin", "BI Developer")


def can_upload_data(role: str) -> bool:
    return role in ("Admin", "BI Developer")


def can_use_llm(role: str) -> bool:
    return role in ("Admin", "BI Developer")


def can_download_outputs(role: str) -> bool:
    return role in ("Admin", "BI Developer")


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
    role: str = "Admin",
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

    if can_upload_data(role):
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
    else:
        st.info("CSV upload is not available in Business Viewer mode.", icon="🔒")

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


def render_semantic_metadata_agent(results: Optional[Dict[str, Any]], role: str = "Admin"):
    st.header("4. Semantic Metadata Agent")

    st.markdown(
        """
        The semantic metadata layer recommends how each field should be interpreted by a
        natural-language BI system. Rule-based generation is available by default,
        and Gemini-assisted enrichment can be enabled with a private API key.
        """
    )

    # --- Mode toggle (Admin / BI Developer only) ---
    if can_use_llm(role):
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

        # Always re-read the current Gemini key status.
        if mode == "LLM-assisted (Gemini)":
            llm_service = GeminiLLMService.from_env()
            st.session_state["llm_service"] = llm_service

            if llm_service.is_available():
                st.success("Gemini API key detected. LLM-assisted mode is active.", icon="✅")
            else:
                st.info(
                    "LLM-assisted mode is available as an optional bring-your-own-key feature. "
                    "This public demo does not include a hosted Gemini API key to prevent unintended API usage. "
                    "To try Gemini enrichment locally, clone the repo, create a Gemini API key in Google AI Studio, "
                    "and add it to `.streamlit/secrets.toml` as `GEMINI_API_KEY`. "
                    "For this hosted demo, the app will safely use rule-based fallback.",
                    icon="ℹ️",
                )
    else:
        st.caption("Metadata generation mode: **Rule-based** (LLM-assisted mode is not available in Business Viewer mode.)")

    if not results:
        if role == "Business Viewer":
            st.info(
                "No pipeline results are available yet. "
                "Results are generated by Admin or BI Developer roles. "
                "Ask your BI team to run the pipeline and share the results.",
                icon="ℹ️",
            )
        else:
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

    if can_download_outputs(role):
        csv = field_suggestions_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Field Suggestions CSV",
            data=csv,
            file_name="field_suggestions.csv",
            mime="text/csv",
        )


def render_question_validation(results: Optional[Dict[str, Any]], role: str = "Admin"):
    st.header("5. Question Validation")

    st.markdown(
        """
        Candidate BI questions are generated from domain context, metric definitions,
        glossary terms, and seed question patterns. They are then scored across
        grounding, relevance, clarity, analytical richness, and usability.
        """
    )

    st.info(
        "Questions are not promoted only because they sound fluent. "
        "They must be grounded in approved fields and metrics, clear enough for business users, "
        "and safe to answer from the selected dataset.",
        icon="ℹ️",
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

    # Include new guardrail columns when present; fall back gracefully if absent
    display_cols = [
        col for col in [
            "promotion_status",
            "guardrail_category",
            "final_score",
            "question_text",
            "suggested_fix",
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
    if can_download_outputs(role):
        st.download_button(
            "Download Promotion Results CSV",
            data=csv,
            file_name="promotion_results.csv",
            mime="text/csv",
        )

    # ------------------------------------------------------------------
    # Admin-only review & fix simulator (session-state only, no persistence)
    # ------------------------------------------------------------------
    if role == "Admin":
        st.divider()
        st.markdown("#### Admin Review & Fix Simulator")
        st.caption(
            "This is a session-only review simulator. "
            "Persistent approval history and audit events will be added in the SQLite/audit phase."
        )

        review_candidates = promotion_df[
            promotion_df["promotion_status"].isin(["review", "reject"])
        ].copy()

        if review_candidates.empty:
            st.success("No questions currently require admin review.")
        else:
            selected_question = st.selectbox(
                "Select a question to review",
                options=review_candidates["question_text"].tolist(),
                key="admin_review_question_select",
            )

            # Show full context for the selected question
            row = review_candidates[
                review_candidates["question_text"] == selected_question
            ].iloc[0]

            # Reset revised question when Admin selects a different original question.
            # This prevents the text area from keeping the previous question's text.
            if st.session_state.get("admin_review_selected_question") != selected_question:
                st.session_state["admin_review_selected_question"] = selected_question
                st.session_state["admin_revised_question"] = selected_question
                st.session_state["admin_reviewer_note"] = ""

            detail_cols = st.columns(3)
            detail_cols[0].metric("Status", row.get("promotion_status", "-"))
            detail_cols[1].metric("Score", row.get("final_score", "-"))
            detail_cols[2].metric(
                "Guardrail",
                str(row.get("guardrail_category", "-")).replace("_", " ").title(),
            )

            st.markdown("**Promotion reason:**")
            st.caption(str(row.get("promotion_reason", "-")))

            fix_text = str(row.get("suggested_fix", ""))
            if fix_text:
                st.markdown("**Suggested fix:**")
                st.caption(fix_text)

            for label, col in [
                ("Deal-breakers", "deal_breakers"),
                ("Easy-to-fix items", "easy_to_fix_items"),
                ("Ambiguity flags", "ambiguity_flags"),
            ]:
                val = row.get(col)
                if val and str(val) not in ("", "[]", "nan", "None"):
                    items = val if isinstance(val, list) else [str(val)]
                    items = [i for i in items if str(i).strip()]
                    if items:
                        st.markdown(
                            f"**{label}:** {'; '.join(ensure_display_sentence(i) for i in items)}"
                        )

            # Revised question text area
            revised_question = st.text_area(
                "Revised question",
                height=80,
                key="admin_revised_question",
                help="Edit the question text before promoting it. The revised version must differ from the original.",
            )

            reviewer_note = st.text_input(
                "Reviewer note (optional)",
                key="admin_reviewer_note",
                placeholder="e.g. Added time window and replaced unregistered metric.",
            )

            admin_action = st.radio(
                "Choose action",
                options=["Promote revised question", "Keep in review", "Reject original question"],
                horizontal=True,
                key="admin_review_action",
            )

            if st.button("Apply Review Decision", key="admin_review_apply"):
                if admin_action == "Promote revised question":
                    if revised_question.strip() == selected_question.strip():
                        st.warning(
                            "Please revise the question before promoting it. "
                            "The original question was not promoted by the guardrail checks."
                        )
                    else:
                        review_log = st.session_state.setdefault("admin_review_log", [])
                        review_log.append({
                            "original_question": selected_question,
                            "revised_question": revised_question.strip(),
                            "original_status": row.get("promotion_status", ""),
                            "action": admin_action,
                            "guardrail_category": row.get("guardrail_category", ""),
                            "suggested_fix": fix_text,
                            "reviewer_note": reviewer_note.strip(),
                        })
                        st.success(
                            f"Revised question promoted: _{revised_question.strip()}_"
                        )
                else:
                    review_log = st.session_state.setdefault("admin_review_log", [])
                    review_log.append({
                        "original_question": selected_question,
                        "revised_question": "",
                        "original_status": row.get("promotion_status", ""),
                        "action": admin_action,
                        "guardrail_category": row.get("guardrail_category", ""),
                        "suggested_fix": fix_text,
                        "reviewer_note": reviewer_note.strip(),
                    })
                    st.success(f"Decision recorded: **{admin_action}**")

            # Show session review log
            review_log = st.session_state.get("admin_review_log", [])
            if review_log:
                st.markdown("##### Session Review Log")
                log_df = pd.DataFrame(review_log)[
                    [c for c in [
                        "action", "original_status", "guardrail_category",
                        "original_question", "revised_question", "reviewer_note",
                    ] if c in pd.DataFrame(review_log).columns]
                ]
                st.dataframe(log_df, use_container_width=True)

                st.markdown("##### Simulated Review Impact")

                impact_df = pd.DataFrame(review_log)

                promoted_count = int(
                    (impact_df["action"] == "Promote revised question").sum()
                )
                review_count = int(
                    (impact_df["action"] == "Keep in review").sum()
                )
                rejected_count = int(
                    (impact_df["action"] == "Reject original question").sum()
                )

                impact_cols = st.columns(3)
                impact_cols[0].metric("Promoted Revised Questions", promoted_count)
                impact_cols[1].metric("Kept in Review", review_count)
                impact_cols[2].metric("Rejected Originals", rejected_count)

                st.caption(
                    "These session-only decisions do not overwrite the original validation results. "
                    "Persistent approval history and verified library updates will be added in the SQLite/audit phase."
                )

                promoted_df = impact_df[
                    impact_df["action"] == "Promote revised question"
                ].copy()

                if not promoted_df.empty:
                    st.markdown("##### Simulated Promoted Questions")

                    promoted_cols = [
                        col for col in [
                            "original_question",
                            "revised_question",
                            "guardrail_category",
                            "reviewer_note",
                        ]
                        if col in promoted_df.columns
                    ]

                    st.dataframe(
                        promoted_df[promoted_cols],
                        use_container_width=True,
                    )


def render_verified_question_library(results: Optional[Dict[str, Any]], role: str = "Admin"):
    st.header("6. Verified Question Library")

    st.markdown(
        """
        The verified question library is the trusted output layer. It separates questions
        that are ready for business use from questions that need review or rejection.
        """
    )

    if not results:
        if role == "Business Viewer":
            st.info(
                "No verified questions are available yet. "
                "Results are generated by Admin or BI Developer roles. "
                "Ask your BI team to run the pipeline and share the results.",
                icon="ℹ️",
            )
        else:
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
            "final_score",
            "question_text",
            "target_metrics",
            "target_dimensions",
            "time_grain",
            "promotion_reason",
            "suggested_fix",
        ]
        if col in verified_df.columns
    ]

    st.metric("Verified Questions", len(verified_df))
    st.dataframe(
        clean_dataframe_for_display(verified_df[display_cols]),
        use_container_width=True,
    )

    if can_download_outputs(role):
        csv = verified_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Verified Questions CSV",
            data=csv,
            file_name="verified_questions.csv",
            mime="text/csv",
        )


def render_analytics_dashboard(results: Optional[Dict[str, Any]], role: str = "Admin"):
    st.header("7. Analytics Dashboard")

    st.markdown(
        """
        This dashboard summarizes semantic quality, validation outcomes, and questions
        that need review before they can be trusted for self-service BI.
        """
    )

    if not results:
        if role == "Business Viewer":
            st.info(
                "No pipeline results are available yet. "
                "Results are generated by Admin or BI Developer roles. "
                "Ask your BI team to run the pipeline and share the results.",
                icon="ℹ️",
            )
        else:
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
    # Guardrail Category Breakdown
    # -----------------------------
    if "guardrail_category" in promotion_df.columns:
        st.markdown("#### Guardrail Category Breakdown")
        st.caption(
            "This chart shows the primary guardrail category assigned to each question."
        )

        guardrail_category_df = (
            promotion_df["guardrail_category"]
            .fillna("unknown")
            .astype(str)
            .str.replace("_", " ")
            .str.title()
            .value_counts()
            .reset_index()
        )
        guardrail_category_df.columns = ["guardrail_category", "question_count"]

        def infer_guardrail_status(label: str) -> str:
            normalized = str(label).strip().lower().replace(" ", "_")

            if normalized == "verified_ready":
                return "verified"

            if normalized in {
                "unsupported_metric",
                "missing_field",
                "unsafe_aggregation",
                "not_answerable_from_dataset",
            }:
                return "reject"

            if normalized in {
                "ambiguous_wording",
                "unclear_time_window",
                "weak_business_relevance",
                "low_operational_actionability",
            }:
                return "review"

            return "review"

        guardrail_category_df["status_group"] = guardrail_category_df[
            "guardrail_category"
        ].apply(infer_guardrail_status)

        category_chart_max = max(guardrail_category_df["question_count"].max(), 1)

        fig_guardrail_category = px.bar(
            guardrail_category_df,
            x="question_count",
            y="guardrail_category",
            text="question_count",
            orientation="h",
            color="status_group",
            color_discrete_map={
                "verified": status_color_map["verified"],
                "review": status_color_map["review"],
                "reject": status_color_map["reject"],
            },
            labels={
                "guardrail_category": "Guardrail Category",
                "question_count": "Number of Questions",
                "status_group": "Validation Status",
            },
        )

        fig_guardrail_category.update_traces(
            textposition="outside",
            textfont=dict(size=16, color=amazon_dark),
            marker_line_width=0,
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Questions: %{x}<extra></extra>",
        )

        fig_guardrail_category.update_layout(
            height=430,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.22,
                xanchor="center",
                x=0.43,
                font=dict(size=15, color=amazon_dark),
                title=None,
            ),
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=90, r=40, t=45, b=130),
            xaxis=dict(
                title=None,
                tickfont=tick_font,
                range=[0, category_chart_max * 1.25],
                showgrid=True,
                gridcolor=soft_gray,
                zeroline=False,
            ),
            yaxis=dict(
                title=None,
                tickfont=tick_font,
                categoryorder="total ascending",
            ),
            annotations=[
                dict(
                    text="Number of Questions",
                    xref="paper",
                    yref="paper",
                    x=0.43,
                    y=-0.23,
                    showarrow=False,
                    font=axis_font,
                )
            ],
            font=chart_font,
        )

        st.plotly_chart(fig_guardrail_category, use_container_width=True)

    # -----------------------------
    # Guardrail / Review Issue Breakdown
    # -----------------------------
    st.markdown("#### Guardrail and Review Issue Breakdown")

    st.caption(
        "Each question is counted once using priority-based buckets. "
        "Deal-breaker issues take priority over easy-to-fix and ambiguity flags."
    )

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

    for col in ["deal_breakers", "easy_to_fix_items", "ambiguity_flags"]:
        if col not in promotion_df.columns:
            promotion_df[col] = None

    deal_breaker_mask = promotion_df["deal_breakers"].apply(has_issue)
    easy_to_fix_mask = promotion_df["easy_to_fix_items"].apply(has_issue)
    ambiguity_mask = promotion_df["ambiguity_flags"].apply(has_issue)

    deal_breaker_count = int(deal_breaker_mask.sum())

    easy_to_fix_only_count = int(
        ((~deal_breaker_mask) & easy_to_fix_mask).sum()
    )

    ambiguity_only_count = int(
        ((~deal_breaker_mask) & (~easy_to_fix_mask) & ambiguity_mask).sum()
    )

    issue_summary_df = pd.DataFrame(
        [
            {
                "issue_bucket": "Deal-breaker questions",
                "question_count": deal_breaker_count,
            },
            {
                "issue_bucket": "Easy-to-fix only",
                "question_count": easy_to_fix_only_count,
            },
            {
                "issue_bucket": "Ambiguity only",
                "question_count": ambiguity_only_count,
            },
        ]
    )

    issue_chart_max = max(issue_summary_df["question_count"].max(), 1)

    fig_issues = px.bar(
        issue_summary_df,
        x="issue_bucket",
        y="question_count",
        text="question_count",
        color_discrete_sequence=[soft_gray_bar],
        labels={
            "issue_bucket": "Issue Bucket",
            "question_count": "Number of Questions",
        },
    )

    fig_issues.update_traces(
        textposition="outside",
        textfont=dict(size=16, color=amazon_dark),
        marker_line_width=0,
        cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Questions: %{y}<extra></extra>",
    )

    fig_issues.update_layout(
        height=390,
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=20, r=20, t=45, b=80),
        xaxis=dict(
            title=dict(text="Issue Bucket", font=axis_font),
            tickfont=tick_font,
            tickangle=0,
        ),
        yaxis=dict(
            range=[0, issue_chart_max * 1.25],
            showgrid=True,
            gridcolor=soft_gray,
            zeroline=False,
            title=dict(text="Number of Questions", font=axis_font),
            tickfont=tick_font,
        ),
        font=chart_font,
    )

    st.plotly_chart(fig_issues, use_container_width=True)

    # -----------------------------
    # Attention Buckets
    # -----------------------------
    st.markdown("#### Questions Requiring Attention")

    st.caption(
        "Questions below are grouped by the highest-priority issue found during validation."
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


def render_monitoring_audit_log(results: Optional[Dict[str, Any]], role: str = "Admin"):
    st.header("8. Monitoring & Audit Log")

    st.markdown(
        """
        This section previews the future audit and feedback loop. The current version shows
        the latest in-session review trail. Phase 5 will add SQLite-backed persistence for
        semantic metadata, question scores, verified questions, and audit events.
        """
    )

    if not results:
        if role == "Business Viewer":
            st.info(
                "No pipeline results are available yet. "
                "Results are generated by Admin or BI Developer roles. "
                "Ask your BI team to run the pipeline and share the results.",
                icon="ℹ️",
            )
        else:
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

    # --- Demo role selector ---
    selected_role = st.selectbox(
        "Demo Role",
        options=_ROLES,
        index=0,
        key="demo_role",
        help="Select a role to simulate how different personas experience the workflow.",
    )

    with st.expander("Role permissions"):
        st.markdown(f"**{selected_role}**")
        st.caption(_ROLE_DESCRIPTIONS[selected_role])

    st.divider()

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

    if can_run_pipeline(selected_role):
        run_button = st.button("Run Pipeline", type="primary")
    else:
        run_button = False
        st.button("Run Pipeline", type="primary", disabled=True,
                  help="Pipeline execution is not available in Business Viewer mode.")

    st.divider()

    # Restrict page list for Business Viewer
    if can_run_pipeline(selected_role):
        available_pages = [
            "1. Business Context",
            "2. Upload / Select Dataset",
            "3. Field Profiling",
            "4. Semantic Metadata Agent",
            "5. Question Validation",
            "6. Verified Question Library",
            "7. Analytics Dashboard",
            "8. Monitoring & Audit Log",
        ]
    else:
        available_pages = sorted(_VIEWER_PAGES)

    page = st.radio(
        "Workflow Navigation",
        available_pages,
        key="workflow_navigation_page",
        on_change=request_scroll_to_top,
    )

    st.divider()
    st.caption(
        "Demo stack: semantic domain packs, optional Gemini enrichment, role-based workflows, "
        "guardrail validation, verified question governance, SQLite audit history, and analytics dashboard."
    )

df, metric_registry, glossary, seed_questions = load_domain_pack(selected_domain)

if st.session_state.get("selected_domain") != selected_domain:
    st.session_state.pop("pipeline_results", None)

if run_button:
    with st.spinner("Running semantic BI workflow..."):
        # Resolve LLM service based on current mode selection.
        # Always re-read from secrets/env to avoid stale disabled service objects.
        selected_mode = st.session_state.get("semantic_mode", "Rule-based")
        active_llm_service = None

        if selected_mode == "LLM-assisted (Gemini)" and can_use_llm(selected_role):
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
        role=selected_role,
    )

elif page == "3. Field Profiling":
    render_field_profiling(results)

elif page == "4. Semantic Metadata Agent":
    render_semantic_metadata_agent(results, role=selected_role)

elif page == "5. Question Validation":
    render_question_validation(results, role=selected_role)

elif page == "6. Verified Question Library":
    render_verified_question_library(results, role=selected_role)

elif page == "7. Analytics Dashboard":
    render_analytics_dashboard(results, role=selected_role)

elif page == "8. Monitoring & Audit Log":
    render_monitoring_audit_log(results, role=selected_role)

# Run the scroll script after all content is rendered.
# This is more reliable than calling it before page content is mounted.
if st.session_state.pop("should_scroll_to_top", False):
    scroll_to_top()