"""
Optional Gemini LLM service for semantic metadata enrichment.

Responsibilities:
- Read GEMINI_API_KEY from Streamlit secrets or environment variables
- Call Gemini to generate enriched field metadata
- Validate the structured response with Pydantic
- Return None on any failure so the caller can fall back to rule-based output

This module never raises exceptions to the caller and never logs the API key.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for structured LLM output
# ---------------------------------------------------------------------------

class LLMFieldMetadata(BaseModel):
    """Validated structured output from the Gemini LLM for a single field."""

    field_name: str
    friendly_name: str
    business_definition: str
    synonyms: List[str]
    default_aggregation: Optional[str] = None
    disallowed_aggregations: List[str]
    data_quality_notes: str
    business_owner_hint: str
    confidence_score: float          # 0.0 – 1.0
    needs_human_review: bool


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class GeminiLLMService:
    """
    Thin wrapper around the google-genai SDK for field metadata enrichment.

    Usage:
        service = GeminiLLMService.from_env()
        if service.is_available():
            metadata = service.enrich_field(profile, glossary_entry, metric_entry)
    """

    _MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: Optional[str]) -> None:
        self._api_key = api_key
        self._client = None

        if api_key:
            try:
                from google import genai  # type: ignore
                self._client = genai.Client(api_key=api_key)
            except Exception:
                # google-genai not installed or key rejected at init time
                self._client = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "GeminiLLMService":
        """
        Build a service instance by reading the API key from:
        1. st.secrets["GEMINI_API_KEY"]  (Streamlit Cloud / local secrets.toml)
        2. os.environ["GEMINI_API_KEY"]
        Returns a disabled instance (is_available() == False) if the key is absent.
        """
        api_key: Optional[str] = None

        # Try Streamlit secrets first (only available when Streamlit is running)
        try:
            import streamlit as st  # type: ignore
            api_key = st.secrets.get("GEMINI_API_KEY") or None
        except Exception:
            pass

        # Fall back to environment variable
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY") or None

        return cls(api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True only when the client was initialised successfully."""
        return self._client is not None

    def enrich_field(
        self,
        field_name: str,
        dtype: str,
        heuristic_role: str,
        sample_values: List[str],
        null_rate: float,
        distinct_count: int,
        glossary_entry: Optional[List[str]],
        metric_entry: Optional[Dict[str, Any]],
        domain_name: str,
        seed_questions: Optional[List[str]] = None,
    ) -> Optional[LLMFieldMetadata]:
        """
        Ask Gemini to generate enriched metadata for a single field.

        Returns a validated LLMFieldMetadata on success, or None on any failure.
        The caller must treat None as a signal to use rule-based output instead.
        """
        if not self.is_available():
            return None

        prompt = self._build_prompt(
            field_name=field_name,
            dtype=dtype,
            heuristic_role=heuristic_role,
            sample_values=sample_values,
            null_rate=null_rate,
            distinct_count=distinct_count,
            glossary_entry=glossary_entry,
            metric_entry=metric_entry,
            domain_name=domain_name,
            seed_questions=seed_questions or [],
        )

        try:
            from google import genai  # type: ignore

            response = self._client.models.generate_content(
                model=self._MODEL,
                contents=prompt,
            )
            raw_text = response.text or ""
            return self._parse_response(raw_text, field_name)

        except Exception as exc:
            # Log at debug level — never surface the key or crash the app
            logger.debug("Gemini call failed for field '%s': %s", field_name, type(exc).__name__)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        field_name: str,
        dtype: str,
        heuristic_role: str,
        sample_values: List[str],
        null_rate: float,
        distinct_count: int,
        glossary_entry: Optional[List[str]],
        metric_entry: Optional[Dict[str, Any]],
        domain_name: str,
        seed_questions: List[str],
    ) -> str:
        glossary_context = (
            f"Glossary synonyms for this field: {', '.join(glossary_entry)}"
            if glossary_entry
            else "No glossary entry found for this field."
        )

        metric_context = (
            f"Metric registry entry: {json.dumps(metric_entry)}"
            if metric_entry
            else "No metric registry entry found for this field."
        )

        seed_context = (
            f"Sample business questions for this domain: {'; '.join(seed_questions[:5])}"
            if seed_questions
            else ""
        )

        return f"""You are a BI semantic layer expert. Generate structured metadata for a single dataset field.

Domain: {domain_name}
Field name: {field_name}
Data type: {dtype}
Heuristic role: {heuristic_role}
Sample values: {', '.join(str(v) for v in sample_values[:5])}
Null rate: {null_rate:.1%}
Distinct count: {distinct_count}
{glossary_context}
{metric_context}
{seed_context}

Return ONLY a valid JSON object with exactly these fields (no markdown, no explanation):
{{
  "field_name": "{field_name}",
  "friendly_name": "<human-readable label>",
  "business_definition": "<one sentence business definition>",
  "synonyms": ["<synonym1>", "<synonym2>"],
  "default_aggregation": "<sum|avg|count|min|max or null>",
  "disallowed_aggregations": ["<agg1>"],
  "data_quality_notes": "<brief note about null rate, cardinality, or data issues>",
  "business_owner_hint": "<suggested team or role that owns this field>",
  "confidence_score": <0.0 to 1.0>,
  "needs_human_review": <true|false>
}}"""

    def _parse_response(self, raw_text: str, field_name: str) -> Optional[LLMFieldMetadata]:
        """Extract JSON from the response and validate it with Pydantic."""
        text = raw_text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        # Find the first { ... } block
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            logger.debug("No JSON object found in Gemini response for field '%s'", field_name)
            return None

        json_str = text[start:end]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.debug("JSON decode error for field '%s': %s", field_name, exc)
            return None

        # Ensure field_name matches to prevent hallucinated field names
        data["field_name"] = field_name

        try:
            return LLMFieldMetadata(**data)
        except ValidationError as exc:
            logger.debug("Pydantic validation failed for field '%s': %s", field_name, exc)
            return None
