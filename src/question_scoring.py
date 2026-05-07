from typing import Any, Dict, List, Optional, Set, Tuple

from .schemas import QuestionCandidate, FieldSuggestion, QuestionScore, ValidationStatus


class QuestionScorer:
    """
    Scores candidate BI questions across multiple quality dimensions for MVP BI workflow.
    Heuristic, not LLM-based.
    """

    def __init__(self):
        pass

    def score(
        self,
        candidate: QuestionCandidate,
        metric_registry: Dict[str, Any],
        glossary: Dict[str, List[str]],
        field_suggestions: List[FieldSuggestion],
    ) -> QuestionScore:
        rationale = {}

        deal_breakers = self._find_deal_breakers(
            candidate=candidate,
            metric_registry=metric_registry,
            field_suggestions=field_suggestions,
        )

        easy_to_fix = self._find_easy_to_fix_items(
            candidate=candidate,
            metric_registry=metric_registry,
            field_suggestions=field_suggestions,
        )

        ambiguity_flags = self._find_ambiguity_flags(candidate)

        grounding_score, rationale["grounding_score"] = self._score_grounding(
            candidate=candidate,
            metric_registry=metric_registry,
            field_suggestions=field_suggestions,
        )

        relevance_score, rationale["relevance_score"] = self._score_relevance(
            candidate=candidate,
            metric_registry=metric_registry,
            field_suggestions=field_suggestions,
        )

        clarity_score, rationale["clarity_score"] = self._score_clarity(
            candidate=candidate,
            metric_registry=metric_registry,
        )

        complexity_score, rationale["complexity_score"] = self._score_complexity(candidate)
        format_score, rationale["format_score"] = self._score_format(candidate)

        final_score = sum(
            [
                grounding_score,
                relevance_score,
                clarity_score,
                complexity_score,
                format_score,
            ]
        )

        if deal_breakers or final_score < 60:
            validation_status = ValidationStatus.REJECT
        elif final_score < 80:
            validation_status = ValidationStatus.REVIEW
        else:
            validation_status = ValidationStatus.VERIFIED

        return QuestionScore(
            grounding_score=grounding_score,
            relevance_score=relevance_score,
            clarity_score=clarity_score,
            complexity_score=complexity_score,
            format_score=final_score if False else format_score,
            final_score=final_score,
            deal_breakers=deal_breakers,
            easy_to_fix_items=easy_to_fix,
            ambiguity_flags=ambiguity_flags,
            evaluator_rationale=rationale,
            validation_status=validation_status,
        )

    def _score_grounding(
        self,
        candidate: QuestionCandidate,
        metric_registry: Dict[str, Any],
        field_suggestions: List[FieldSuggestion],
    ) -> Tuple[float, str]:
        if not candidate.question_text.strip():
            return 0, "Question text is empty."

        if not candidate.target_metrics:
            return 0, "No target metric specified."

        field_names = self._get_included_field_names(field_suggestions)
        registered_metric_names = self._get_available_metric_names(metric_registry)

        missing_metrics = [
            metric
            for metric in candidate.target_metrics
            if metric not in registered_metric_names
        ]

        missing_dimensions = [
            dim
            for dim in candidate.target_dimensions
            if dim not in field_names
        ]

        if missing_metrics:
            return 5, "Target metric is not mapped to the official metric registry."

        if missing_dimensions:
            return 5, "Target dimension is not available in the semantic layer."

        return 20, "All target metrics and dimensions are grounded in the metric registry and semantic layer."

    def _score_relevance(
        self,
        candidate: QuestionCandidate,
        metric_registry: Dict[str, Any],
        field_suggestions: List[FieldSuggestion],
    ) -> Tuple[float, str]:
        if not candidate.target_metrics:
            return 0, "No metric specified."

        if not self._target_metrics_registered(candidate, metric_registry):
            return 5, "Metric is not mapped to a registered business metric."

        if candidate.target_dimensions and self._has_analytical_intent(candidate.question_text):
            return 20, "Registered metric with a clear analytical intent and business dimension."

        if self._has_analytical_intent(candidate.question_text):
            return 17, "Registered metric with a clear analytical intent."

        return 14, "Registered metric, but the analytical intent is not very specific."

    def _score_clarity(
        self,
        candidate: QuestionCandidate,
        metric_registry: Dict[str, Any],
    ) -> Tuple[float, str]:
        text = candidate.question_text.strip()
        text_lower = text.lower()

        if not text:
            return 0, "Question text is empty."

        if not candidate.target_metrics:
            return 6, "Question does not specify a target metric."

        if self._is_low_information_question(text_lower):
            return 6, "Question is too broad and does not specify a useful BI task."

        if len(text_lower) < 15:
            return 10, "Question wording is too short to be reliable."

        has_registered_metric = self._target_metrics_registered(candidate, metric_registry)
        has_dimension = bool(candidate.target_dimensions)
        has_intent = self._has_analytical_intent(text_lower)

        if has_registered_metric and has_dimension and has_intent:
            return 20, "Question uses a registered metric, a clear dimension, and a recognizable analytical intent."

        if has_registered_metric and has_intent:
            return 17, "Question uses a registered metric and a recognizable analytical intent."

        if has_registered_metric and has_dimension:
            return 16, "Question uses a registered metric and a clear business dimension."

        if not has_dimension and self._usually_needs_dimension(text_lower):
            return 12, "Question lacks a clear comparison or breakdown dimension."

        if not has_intent:
            return 12, "Question lacks a clear analytical intent such as trend, comparison, breakdown, top, or bottom analysis."

        return 14, "Question is understandable but may need more specific business context."

    def _score_complexity(self, candidate: QuestionCandidate) -> Tuple[float, str]:
        n_dims = len(candidate.target_dimensions)
        n_filters = len(candidate.filters)

        if n_dims == 0 and n_filters == 0:
            return 8, "No breakdown dimension or filter."

        if n_dims > 3 or n_filters > 3:
            return 10, "Too many breakdowns or filters for a verified starter question."

        if n_dims >= 2 or n_filters >= 2:
            return 18, "Good analytical richness without being too complex."

        return 15, "Simple but valid analytical structure."

    def _score_format(self, candidate: QuestionCandidate) -> Tuple[float, str]:
        text = candidate.question_text.lower()

        if candidate.time_grain:
            return 20, "Time grain is specified."

        if self._has_time_context(text, candidate.time_grain):
            return 20, "Question includes a recognizable time context."

        if "trend" in text:
            return 15, "Trend question is understandable, but the time grain is not explicitly structured."

        return 12, "Question does not include a clear time context."

    def _find_deal_breakers(
        self,
        candidate: QuestionCandidate,
        metric_registry: Dict[str, Any],
        field_suggestions: List[FieldSuggestion],
    ) -> List[str]:
        breakers = []

        if not candidate.question_text.strip():
            breakers.append("Question text is empty.")

        if not candidate.target_metrics:
            breakers.append("No target metric specified.")

        field_names = self._get_included_field_names(field_suggestions)
        registered_metric_names = self._get_available_metric_names(metric_registry)

        for metric in candidate.target_metrics:
            if metric not in registered_metric_names:
                breakers.append(
                    f"Metric '{metric}' is not mapped to a registered business metric."
                )

        for dimension in candidate.target_dimensions:
            if dimension not in field_names:
                breakers.append(
                    f"Dimension '{dimension}' is not available in the semantic layer."
                )

        return breakers

    def _find_easy_to_fix_items(
        self,
        candidate: QuestionCandidate,
        metric_registry: Dict[str, Any],
        field_suggestions: List[FieldSuggestion],
    ) -> List[str]:
        fixes = []
        text = candidate.question_text.lower()

        if not self._has_time_context(text, candidate.time_grain):
            fixes.append("Question lacks a clear time context.")

        if self._uses_date_as_regular_dimension(candidate):
            fixes.append("Date field is used as a regular comparison dimension.")

        if not candidate.target_dimensions and self._usually_needs_dimension(text):
            fixes.append("Question lacks a clear comparison or breakdown dimension.")

        if not self._has_analytical_intent(text):
            fixes.append("Question lacks a clear analytical intent.")

        if self._is_low_information_question(text):
            fixes.append("Question is too broad to be promoted without a clearer BI task.")

        return self._dedupe_list(fixes)

    def _find_ambiguity_flags(self, candidate: QuestionCandidate) -> List[str]:
        flags = []
        text = candidate.question_text.lower()

        if "recent" in text and not self._has_specific_time_window(text):
            flags.append("Recent is ambiguous without a specific time window.")

        if not candidate.target_metrics:
            flags.append("Metric or aggregation is unclear.")

        if any(word in text for word in ["performance", "impact", "effect"]):
            flags.append("Business term is broad and may need clarification.")

        return self._dedupe_list(flags)

    def _get_available_metric_names(self, metric_registry: Dict[str, Any]) -> Set[str]:
        metric_names = set()

        if not metric_registry:
            return metric_names

        if "metrics" in metric_registry and isinstance(metric_registry["metrics"], list):
            for metric in metric_registry["metrics"]:
                if isinstance(metric, dict):
                    name = metric.get("name")
                    if name:
                        metric_names.add(str(name))
            return metric_names

        for key in metric_registry.keys():
            metric_names.add(str(key))

        return metric_names

    def _target_metrics_registered(
        self,
        candidate: QuestionCandidate,
        metric_registry: Dict[str, Any],
    ) -> bool:
        if not candidate.target_metrics:
            return False

        available_metric_names = self._get_available_metric_names(metric_registry)
        return all(metric in available_metric_names for metric in candidate.target_metrics)

    def _get_included_field_names(self, field_suggestions: List[FieldSuggestion]) -> Set[str]:
        return {field.field_name for field in field_suggestions if field.include}

    def _has_analytical_intent(self, text: str) -> bool:
        text = text.lower()
        intent_terms = [
            "trend",
            "over time",
            "compare",
            "comparison",
            "across",
            "breakdown",
            "broken down",
            "by ",
            "highest",
            "lowest",
            "top",
            "bottom",
            "increase",
            "decrease",
            "change",
            "vary",
            "varies",
            "differ",
            "difference",
        ]
        return any(term in text for term in intent_terms)

    def _has_time_context(self, text: str, time_grain: Optional[str] = None) -> bool:
        if time_grain:
            return True

        text = text.lower()
        time_terms = [
            "last month",
            "last week",
            "last 30 days",
            "last 4 weeks",
            "current quarter",
            "this quarter",
            "over time",
            "trend",
            "weekly",
            "monthly",
            "quarterly",
            "yearly",
        ]

        return any(term in text for term in time_terms)

    def _has_specific_time_window(self, text: str) -> bool:
        text = text.lower()
        specific_time_terms = [
            "last month",
            "last week",
            "last 30 days",
            "last 4 weeks",
            "current quarter",
            "this quarter",
            "weekly",
            "monthly",
            "quarterly",
            "yearly",
        ]
        return any(term in text for term in specific_time_terms)

    def _usually_needs_dimension(self, text: str) -> bool:
        text = text.lower()
        dimension_intent_terms = [
            "compare",
            "comparison",
            "across",
            "breakdown",
            "broken down",
            "highest",
            "lowest",
            "top",
            "bottom",
            "vary",
            "varies",
            "differ",
            "difference",
        ]
        return any(term in text for term in dimension_intent_terms)

    def _uses_date_as_regular_dimension(self, candidate: QuestionCandidate) -> bool:
        text = candidate.question_text.lower()

        if "trend" in text or "over time" in text:
            return False

        return any(
            "date" in dimension.lower()
            or "time" in dimension.lower()
            or dimension.lower().endswith("_ts")
            for dimension in candidate.target_dimensions
        )

    def _is_low_information_question(self, text: str) -> bool:
        normalized = " ".join(text.lower().strip().split())

        low_information_patterns = [
            "show me data",
            "show data",
            "show me the data",
            "show info",
            "show information",
            "show me information",
            "what is the data",
            "give me data",
        ]

        return any(pattern in normalized for pattern in low_information_patterns)

    def _dedupe_list(self, items: List[str]) -> List[str]:
        seen = set()
        deduped = []

        for item in items:
            normalized = item.strip().rstrip(".").lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(item.strip().rstrip("."))

        return deduped


"""
Optional LLM-based scorer placeholder for a later phase.

This is intentionally not used by the heuristic MVP pipeline.
"""


class LLMQuestionScorer:
    """Scores BI questions for quality and relevance using an LLM in a later phase."""

    def __init__(self, model: str = "gpt-4"):
        self.model = model

    def score(self, question: str, schema: dict = None) -> dict:
        """
        Placeholder for future LLM-based scoring.

        Args:
            question: Natural language question.
            schema: Optional data schema for context.

        Returns:
            Dictionary with score and feedback.
        """
        # TODO: Implement optional LLM-based scoring logic in Phase 2.
        return {}