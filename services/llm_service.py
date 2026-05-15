"""
Optional Google Gemini integration for semantic metadata generation.

This service is intentionally defensive:
- reads GEMINI_API_KEY from Streamlit secrets first, then environment variables
- never exposes or logs the API key
- returns None on any LLM failure so the app can fall back to rule-based output
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import streamlit as st
from pydantic import BaseModel, Field, ValidationError


class SemanticMetadataLLMOutput(BaseModel):
    field_name: str
    friendly_name: str
    business_definition: str
    synonyms: List[str] = Field(default_factory=list)
    default_aggregation: Optional[str] = None
    disallowed_aggregations: List[str] = Field(default_factory=list)
    data_quality_notes: List[str] = Field(default_factory=list)
    business_owner_hint: Optional[str] = None
    confidence_score: float = 0.0
    needs_human_review: bool = True


class GeminiLLMService:
    """Small wrapper around Google Gemini for optional semantic metadata enrichment."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
    ):
        self._api_key = api_key
        self._model_name = model_name
        self._client = None
        self._init_error = None

        if self._api_key:
            self._initialize_client()

    @classmethod
    def from_env(cls) -> "GeminiLLMService":
        """Create a service using Streamlit secrets first, then environment variables."""
        api_key = None

        try:
            api_key = st.secrets.get("GEMINI_API_KEY") or None
        except Exception:
            api_key = None

        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY") or None

        return cls(api_key=api_key)

    def _initialize_client(self) -> None:
        """Initialize Gemini client. Keep failures internal so the app can fall back."""
        try:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
            self._init_error = None
        except Exception as exc:
            self._client = None
            self._init_error = str(exc)

    def is_available(self) -> bool:
        """Return True only when an API key exists and the Gemini client initialized."""
        return bool(self._api_key and self._client)

    def enrich_field(
        self,
        field_profile: Any,
        metric_registry: Optional[Dict[str, Any]] = None,
        glossary: Optional[Dict[str, Any]] = None,
        domain_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Generate semantic metadata for one field.

        Returns:
            dict if Gemini succeeds and output passes validation
            None if unavailable or invalid, allowing rule-based fallback
        """
        if not self.is_available():
            return None

        field_context = self._normalize_field_profile(field_profile)
        prompt = self._build_prompt(
            field_context=field_context,
            metric_registry=metric_registry or {},
            glossary=glossary or {},
            domain_name=domain_name,
        )

        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
            )

            response_text = getattr(response, "text", None)
            if not response_text:
                return None

            parsed_json = self._extract_json(response_text)
            if not parsed_json:
                return None

            validated = SemanticMetadataLLMOutput(**parsed_json)
            return validated.model_dump()

        except (ValidationError, Exception):
            return None

    def _normalize_field_profile(self, field_profile: Any) -> Dict[str, Any]:
        """Convert Pydantic object, dict, or generic object into a plain dict."""
        if hasattr(field_profile, "model_dump"):
            return field_profile.model_dump()

        if hasattr(field_profile, "dict"):
            return field_profile.dict()

        if isinstance(field_profile, dict):
            return field_profile

        return {"field_name": str(field_profile)}

    def _build_prompt(
        self,
        field_context: Dict[str, Any],
        metric_registry: Dict[str, Any],
        glossary: Dict[str, Any],
        domain_name: str,
    ) -> str:
        field_name = field_context.get("field_name", "")

        grounding_context = {
            "domain_name": domain_name,
            "field_profile": field_context,
            "metric_registry": metric_registry,
            "glossary_entry_for_field": glossary.get(field_name),
        }

        return f"""
You are helping a Business Intelligence team create governed semantic metadata for a natural-language BI layer.

Use the provided domain context as grounding. If the metric registry or glossary already includes information for the field, use it instead of inventing a conflicting definition.

Return ONLY valid JSON. Do not include markdown, code fences, or explanatory prose.

Required JSON schema:
{{
  "field_name": "string",
  "friendly_name": "string",
  "business_definition": "string",
  "synonyms": ["string"],
  "default_aggregation": "sum | average | count | count_distinct | none | null",
  "disallowed_aggregations": ["string"],
  "data_quality_notes": ["string"],
  "business_owner_hint": "string or null",
  "confidence_score": 0.0,
  "needs_human_review": true
}}

Rules:
- confidence_score must be between 0 and 1.
- Use needs_human_review=true when the field meaning, aggregation, or business use is uncertain.
- For identifiers, default_aggregation should usually be null or count_distinct.
- For dates and dimensions, default_aggregation should usually be null.
- For additive numeric metrics, default_aggregation can be sum.
- For rates, percentages, averages, and ratios, default_aggregation should usually be average and sum should be disallowed.
- Keep the output concise and business-readable.

Grounding context:
{json.dumps(grounding_context, indent=2, default=str)}
""".strip()

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract a JSON object from model output."""
        cleaned = text.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None

        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
