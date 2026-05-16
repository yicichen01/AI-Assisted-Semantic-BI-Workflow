"""
Promotion rules for candidate BI question validation.

Responsibilities:
- Apply final threshold-based promotion logic to scored candidate questions
- Convert validation scores, deal breakers, and ambiguity flags into Verified / Review / Reject decisions
- Generate actionable review reasons and suggested fixes for BI owners
- Classify each outcome into a named guardrail category for dashboard surfacing
"""

import re
from typing import List, Tuple

from src.schemas import QuestionScore, ValidationStatus

# ---------------------------------------------------------------------------
# Guardrail category constants
# ---------------------------------------------------------------------------
GUARDRAIL_MISSING_FIELD = "missing_field"
GUARDRAIL_UNSUPPORTED_METRIC = "unsupported_metric"
GUARDRAIL_UNSAFE_AGGREGATION = "unsafe_aggregation"
GUARDRAIL_AMBIGUOUS_WORDING = "ambiguous_wording"
GUARDRAIL_UNCLEAR_TIME_WINDOW = "unclear_time_window"
GUARDRAIL_WEAK_RELEVANCE = "weak_business_relevance"
GUARDRAIL_LOW_ACTIONABILITY = "low_operational_actionability"
GUARDRAIL_NOT_ANSWERABLE = "not_answerable_from_dataset"
GUARDRAIL_VERIFIED = "verified_ready"


class PromotionRules:
    """Apply final business rules to scored candidate questions."""

    def apply(self, score: QuestionScore) -> Tuple[ValidationStatus, str, str, str]:
        """
        Return (promotion_status, promotion_reason, guardrail_category, suggested_fix).

        promotion_reason:
            Concise sentence for table display.

        suggested_fix:
            Actionable fix for review/reject questions.
            Empty string for verified questions.
        """
        if score.deal_breakers:
            category = self._classify_guardrail_from_deal_breakers(score.deal_breakers)
            suggested_fix = self._suggest_action_for_deal_breakers(score.deal_breakers)
            reason = self._short_reason_for_category(category)
            return (
                ValidationStatus.REJECT,
                reason,
                category,
                suggested_fix,
            )

        if score.grounding_score < 15:
            suggested_fix = (
                "Use metrics and dimensions that are included in the semantic layer, "
                "or add missing fields to the metric registry."
            )
            return (
                ValidationStatus.REJECT,
                "Not answerable from the current dataset.",
                GUARDRAIL_NOT_ANSWERABLE,
                self._ensure_sentence(suggested_fix),
            )

        if score.final_score < 60:
            suggested_fix = (
                "Rewrite the question so it has a registered metric, "
                "a clear business dimension, and a clear analytical intent."
            )
            return (
                ValidationStatus.REJECT,
                "Question is too broad for operational decision-making.",
                GUARDRAIL_LOW_ACTIONABILITY,
                self._ensure_sentence(suggested_fix),
            )

        if score.clarity_score < 12:
            clarity_reason = score.evaluator_rationale.get(
                "clarity_score",
                "The question wording may be vague or underspecified.",
            )
            clarity_reason = self._clean_sentence(clarity_reason)
            suggested_fix = self._suggest_action_for_clarity_issue(clarity_reason)
            category = self._classify_guardrail_from_clarity(clarity_reason)
            return (
                ValidationStatus.REVIEW,
                self._short_reason_for_category(category),
                category,
                suggested_fix,
            )

        if score.easy_to_fix_items:
            suggested_fix = self._suggest_action_for_fixable_issues(score.easy_to_fix_items)
            category = self._classify_guardrail_from_easy_fixes(score.easy_to_fix_items)
            return (
                ValidationStatus.REVIEW,
                self._short_reason_for_category(category),
                category,
                suggested_fix,
            )

        if score.ambiguity_flags:
            suggested_fix = self._suggest_action_for_ambiguity(score.ambiguity_flags)
            return (
                ValidationStatus.REVIEW,
                "Question wording is ambiguous.",
                GUARDRAIL_AMBIGUOUS_WORDING,
                suggested_fix,
            )

        if 60 <= score.final_score < 85:
            suggested_fix = (
                "Strengthen the question by making the business purpose, "
                "metric, or comparison dimension more explicit."
            )
            return (
                ValidationStatus.REVIEW,
                "Weak business relevance needs a stronger analytical focus.",
                GUARDRAIL_WEAK_RELEVANCE,
                self._ensure_sentence(suggested_fix),
            )

        return (
            ValidationStatus.VERIFIED,
            "Grounded in approved metric and dimension.",
            GUARDRAIL_VERIFIED,
            "",
        )

    # ------------------------------------------------------------------
    # Short concise reason labels for table display
    # ------------------------------------------------------------------

    def _short_reason_for_category(self, category: str) -> str:
        reason = {
            GUARDRAIL_MISSING_FIELD: "Field or dimension is not available.",
            GUARDRAIL_UNSUPPORTED_METRIC: "Metric is not registered.",
            GUARDRAIL_UNSAFE_AGGREGATION: "Aggregation is not safe for this field.",
            GUARDRAIL_AMBIGUOUS_WORDING: "Question wording is ambiguous.",
            GUARDRAIL_UNCLEAR_TIME_WINDOW: "Time window needs clarification.",
            GUARDRAIL_WEAK_RELEVANCE: "Weak business relevance needs a stronger analytical focus.",
            GUARDRAIL_LOW_ACTIONABILITY: "Question is too broad for operational decision-making.",
            GUARDRAIL_NOT_ANSWERABLE: "Not answerable from the current dataset.",
            GUARDRAIL_VERIFIED: "Grounded in approved metric and dimension.",
        }.get(category, "Needs review.")

        return self._ensure_sentence(reason)

    # ------------------------------------------------------------------
    # Guardrail classification helpers
    # ------------------------------------------------------------------

    def _classify_guardrail_from_deal_breakers(self, issues: List[str]) -> str:
        text = " ".join(issues).lower()

        if "metric" in text and "not mapped" in text:
            return GUARDRAIL_UNSUPPORTED_METRIC

        if "dimension" in text and "not available" in text:
            return GUARDRAIL_MISSING_FIELD

        if "field" in text and ("not available" in text or "missing" in text):
            return GUARDRAIL_MISSING_FIELD

        if "aggregation" in text:
            return GUARDRAIL_UNSAFE_AGGREGATION

        if "empty" in text or "not answerable" in text:
            return GUARDRAIL_NOT_ANSWERABLE

        return GUARDRAIL_NOT_ANSWERABLE

    def _classify_guardrail_from_clarity(self, clarity_reason: str) -> str:
        reason = clarity_reason.lower()

        if "time" in reason or "grain" in reason or "period" in reason:
            return GUARDRAIL_UNCLEAR_TIME_WINDOW

        if "dimension" in reason or "breakdown" in reason or "comparison" in reason:
            return GUARDRAIL_MISSING_FIELD

        if "metric" in reason:
            return GUARDRAIL_UNSUPPORTED_METRIC

        return GUARDRAIL_AMBIGUOUS_WORDING

    def _classify_guardrail_from_easy_fixes(self, issues: List[str]) -> str:
        text = " ".join(issues).lower()

        if "time" in text or "grain" in text or "period" in text:
            return GUARDRAIL_UNCLEAR_TIME_WINDOW

        if "dimension" in text:
            return GUARDRAIL_MISSING_FIELD

        if "metric" in text:
            return GUARDRAIL_UNSUPPORTED_METRIC

        if "aggregation" in text or "date field" in text:
            return GUARDRAIL_UNSAFE_AGGREGATION

        return GUARDRAIL_AMBIGUOUS_WORDING

    # ------------------------------------------------------------------
    # Suggested fix helpers
    # ------------------------------------------------------------------

    def _suggest_action_for_deal_breakers(self, issues: List[str]) -> str:
        issue_text = " ".join(issues).lower()
        suggestions = []

        # Extract unsupported metric names from messages like:
        # "Metric 'revenue' is not mapped to a registered business metric."
        metric_names = re.findall(
            r"metric '([^']+)' is not mapped",
            " ".join(issues),
            re.IGNORECASE,
        )

        if metric_names:
            names_str = ", ".join(f"'{metric}'" for metric in metric_names)
            suggestions.append(
                f"This question should remain rejected unless the unsupported metric "
                f"({names_str}) is added to the metric registry or replaced with an approved metric."
            )

        elif "metric" in issue_text:
            suggestions.append(
                "Map the question to a metric in the metric registry, "
                "or add a new metric definition before promotion."
            )

        if "dimension" in issue_text:
            suggestions.append(
                "Use a dimension that exists in the semantic layer, "
                "or include the missing dimension in field setup."
            )

        if "field" in issue_text and ("missing" in issue_text or "not available" in issue_text):
            suggestions.append(
                "Use a field that exists in the semantic layer, "
                "or add the missing field to semantic setup before promotion."
            )

        if "aggregation" in issue_text:
            suggestions.append(
                "Use an aggregation that is approved for the selected metric or field."
            )

        if "empty" in issue_text or "not answerable" in issue_text:
            suggestions.append(
                "Rewrite the question so it can be answered from the available dataset and semantic layer."
            )

        if not suggestions:
            suggestions.append(
                "Resolve the blocking issue before adding the question to the verified library."
            )

        return self._dedupe_join(suggestions)

    def _suggest_action_for_clarity_issue(self, clarity_reason: str) -> str:
        reason = clarity_reason.lower()
        suggestions = []

        if "time" in reason or "grain" in reason or "period" in reason:
            suggestions.append(
                "Add a clear time context, such as last 30 days, last month, current quarter, or over time."
            )

        if "metric" in reason:
            suggestions.append(
                "Map the wording to a registered business metric, or rewrite the metric phrase more explicitly."
            )

        if "dimension" in reason or "breakdown" in reason or "comparison" in reason:
            suggestions.append(
                "Add a clear business dimension, such as site, region, team, shift, cohort, or tenure band."
            )

        if "generic" in reason or "vague" in reason:
            suggestions.append(
                "Make the analytical intent more specific, such as trend, breakdown, comparison, "
                "top performers, or lowest performers."
            )

        if not suggestions:
            suggestions.append(
                "Revise the wording so the metric, dimension, and analytical intent are clear enough for a verified question."
            )

        return self._dedupe_join(suggestions)

    def _suggest_action_for_fixable_issues(self, issues: List[str]) -> str:
        issue_text = " ".join(issues).lower()
        suggestions = []

        if "time" in issue_text or "grain" in issue_text or "period" in issue_text:
            suggestions.append(
                "Add a clear time context, such as last 30 days, last month, last week, current quarter, or over time."
            )

        if "metric is not mapped" in issue_text or "registered business metric" in issue_text:
            suggestions.append(
                "Map the metric phrase to an existing metric in the metric registry, or add a new metric definition."
            )

        if "dimension" in issue_text and "date field" not in issue_text:
            suggestions.append(
                "Add a clear business dimension, such as site, region, team, shift, cohort, or tenure band."
            )

        if "date field" in issue_text:
            suggestions.append(
                "Use the date field for trend analysis or filtering instead of treating it as a regular comparison dimension."
            )

        if "vague" in issue_text or "generic" in issue_text:
            suggestions.append(
                "Rewrite the question with a more specific analytical intent, such as trend, breakdown, "
                "comparison, top performers, or lowest performers."
            )

        if not suggestions:
            suggestions.append(
                "Review the listed issue and revise the question before promoting it to the verified library."
            )

        return self._dedupe_join(suggestions)

    def _suggest_action_for_ambiguity(self, issues: List[str]) -> str:
        issue_text = " ".join(issues).lower()
        suggestions = []

        if "time" in issue_text or "period" in issue_text:
            suggestions.append(
                "Clarify the intended time range, such as last week, last month, or current quarter."
            )

        if "aggregation" in issue_text:
            suggestions.append(
                "Specify the intended aggregation, such as average, total, rate, or count."
            )

        if "metric" in issue_text:
            suggestions.append(
                "Clarify which registered metric the question should use."
            )

        if "business" in issue_text or "entity" in issue_text:
            suggestions.append(
                "Clarify the business entity, such as site, team, manager, shift, cohort, or tenure band."
            )

        if not suggestions:
            suggestions.append(
                "Clarify the ambiguous term before promoting this question to the verified library."
            )

        return self._dedupe_join(suggestions)

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_issues(self, issues: List[str], max_items: int = 3) -> str:
        cleaned = [
            self._clean_sentence(item)
            for item in issues[:max_items]
            if str(item).strip()
        ]
        return "; ".join(self._ensure_sentence(item) for item in cleaned)

    def _clean_sentence(self, text: str) -> str:
        return str(text).strip().rstrip(".")

    def _ensure_sentence(self, text: str) -> str:
        cleaned = str(text).strip()

        if not cleaned:
            return ""

        cleaned = cleaned.rstrip(".")

        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]

        return f"{cleaned}."

    def _dedupe_join(self, suggestions: List[str]) -> str:
        seen = set()
        unique_suggestions = []

        for suggestion in suggestions:
            cleaned = self._clean_sentence(suggestion)
            key = cleaned.lower()

            if cleaned and key not in seen:
                seen.add(key)
                unique_suggestions.append(cleaned)

        return " ".join(self._ensure_sentence(item) for item in unique_suggestions)
