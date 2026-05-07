"""
Semantic Agent for understanding business context and data semantics.

Responsibilities:
- Map natural language to semantic layer entities
- Understand business context and relationships
- Recommend semantic enrichments
- Bridge domain knowledge with technical schema
"""

from typing import List, Dict, Any, Optional
from .schemas import FieldProfile, FieldSuggestion

class SemanticAgent:
    """
    Generates first-pass semantic setup suggestions for BI fields using improved heuristics.
    Modular design for later LLM integration.
    """

    def __init__(self):
        pass

    def suggest_fields(
        self,
        field_profiles: List[FieldProfile],
        metric_registry: Optional[Dict[str, Any]] = None,
        glossary: Optional[Dict[str, List[str]]] = None,
        seed_questions: Optional[List[str]] = None
    ) -> List[FieldSuggestion]:
        """
        Generate semantic suggestions for BI fields.
        """
        seed_questions = seed_questions or []
        glossary = glossary or {}
        metric_registry = metric_registry or {}

        question_text = " ".join(seed_questions).lower()

        suggestions = []
        for profile in field_profiles:
            name = profile.field_name
            name_lower = name.lower()
            dtype = profile.dtype
            role = profile.heuristic_role

            # --- ID fields ---
            if role == "id":
                include = False
                field_role = "id"
                default_aggregation = None
                disallowed_aggregations = ["sum", "avg", "min", "max"]
                # Allow count for IDs
                format_ = None
            # --- Date fields ---
            elif role == "date":
                include = True
                field_role = "date"
                default_aggregation = None
                disallowed_aggregations = ["sum", "avg"]
                format_ = "yyyy-mm-dd"
            # --- Measure fields ---
            elif role == "measure":
                include = True
                field_role = "measure"
                default_aggregation = self._choose_default_aggregation(name_lower, metric_registry)
                disallowed_aggregations = ["count"] if default_aggregation else []
                format_ = None
            # --- Flag fields ---
            elif role == "flag":
                include = True
                field_role = "flag"
                default_aggregation = "count"
                disallowed_aggregations = ["sum", "avg", "min", "max"]
                format_ = None
            # --- Dimension fields ---
            else:
                include = True
                field_role = "dimension"
                default_aggregation = None
                disallowed_aggregations = ["sum", "avg", "min", "max"]
                format_ = None

            # Friendly name
            friendly_name = name.replace("_", " ").title()

            # Synonyms
            synonyms = self._lookup_synonyms(name, glossary)

            # Confidence scoring
            confidence = self._base_confidence(role)
            if self._field_mentioned_in_questions(name_lower, question_text):
                confidence += 0.15
            if self._field_used_in_metrics(name_lower, metric_registry):
                confidence += 0.15
            if synonyms:
                confidence += 0.1
            confidence = min(max(confidence, 0.0), 1.0)

            # Rationale
            rationale = self._build_rationale(role, name, metric_registry, synonyms, question_text)

            suggestion = FieldSuggestion(
                field_name=name,
                include=include,
                friendly_name=friendly_name,
                synonyms=synonyms,
                field_role=field_role,
                default_aggregation=default_aggregation,
                disallowed_aggregations=disallowed_aggregations,
                format=format_,
                confidence=confidence,
                rationale=rationale
            )
            suggestions.append(suggestion)

        return suggestions

    def _choose_default_aggregation(self, name_lower: str, metric_registry: Dict[str, Any]) -> Optional[str]:
        # Use metric_registry if it suggests a preferred aggregation
        for metric, meta in metric_registry.items():
            if name_lower == metric.lower():
                agg = meta.get("aggregation")
                if agg:
                    return agg
        # Heuristic by field name
        avg_keywords = ["rate", "ratio", "pct", "percentage", "percent", "score", "utilization", "compliance", "average", "avg"]
        sum_keywords = ["count", "total", "amount", "volume", "quantity", "minutes", "hours", "revenue", "cost"]
        for kw in avg_keywords:
            if kw in name_lower:
                return "avg"
        for kw in sum_keywords:
            if kw in name_lower:
                return "sum"
        # Default fallback
        return "sum"

    def _lookup_synonyms(self, name: str, glossary: Dict[str, List[str]]) -> List[str]:
        # Try exact and lowercase lookup, remove duplicates
        synonyms = set()
        if name in glossary:
            synonyms.update(glossary[name])
        name_lower = name.lower()
        if name_lower in glossary:
            synonyms.update(glossary[name_lower])
        return sorted(synonyms)

    def _field_mentioned_in_questions(self, name_lower: str, question_text: str) -> bool:
        return name_lower in question_text

    def _field_used_in_metrics(self, name_lower: str, metric_registry: Dict[str, Any]) -> bool:
        for metric, meta in metric_registry.items():
            # Check if field is a metric, in dependencies, or in description
            if name_lower == metric.lower():
                return True
            if "fields" in meta and any(name_lower == f.lower() for f in meta["fields"]):
                return True
            if "description" in meta and name_lower in meta["description"].lower():
                return True
        return False

    def _base_confidence(self, role: str) -> float:
        # Set a base confidence by role
        if role == "id":
            return 0.4
        if role == "date":
            return 0.7
        if role == "measure":
            return 0.7
        if role == "flag":
            return 0.6
        return 0.6

    def _build_rationale(self, role: str, name: str, metric_registry: Dict[str, Any], synonyms: List[str], question_text: str) -> str:
        rationale = ""
        if role == "id":
            rationale = "Field is an identifier and excluded from analysis."
        elif role == "date":
            rationale = "Field is a date/time and included for time-based analysis."
        elif role == "measure":
            rationale = "Field is numeric and suitable for aggregation as a measure."
        elif role == "flag":
            rationale = "Field is binary and can be used as a flag or filter."
        else:
            rationale = "Field is categorical and included as a dimension."
        # Add metric usage
        name_lower = name.lower()
        if self._field_used_in_metrics(name_lower, metric_registry):
            rationale += " Used in metric definitions."
        # Add synonyms
        if synonyms:
            rationale += " Synonyms found in glossary."
        # Add seed question mention
        if self._field_mentioned_in_questions(name_lower, question_text):
            rationale += " Mentioned in seed questions."
        return rationale.strip()
