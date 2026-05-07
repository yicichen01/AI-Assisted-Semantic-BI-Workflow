from typing import List, Tuple

from src.schemas import QuestionScore, ValidationStatus


class PromotionRules:
    """Apply final business rules to scored candidate questions."""

    def apply(self, score: QuestionScore) -> Tuple[ValidationStatus, str]:
        """Return final promotion status and an actionable decision reason."""

        if score.deal_breakers:
            issues = self._format_issues(score.deal_breakers)
            suggestion = self._suggest_action_for_deal_breakers(score.deal_breakers)
            return (
                ValidationStatus.REJECT,
                f"Rejected: blocking issue found - {issues}. Suggested action: {suggestion}"
            )

        if score.grounding_score < 15:
            return (
                ValidationStatus.REJECT,
                f"Rejected: grounding score is too low ({score.grounding_score:.0f}/20). "
                "Suggested action: use metrics and dimensions that are included in the semantic layer or add missing fields to the metric registry."
            )

        if score.final_score < 60:
            return (
                ValidationStatus.REJECT,
                f"Rejected: final score is below the minimum threshold ({score.final_score:.0f}/100). "
                "Suggested action: rewrite the question so it has a registered metric, a clear business dimension, and a clear analytical intent."
            )

        if score.clarity_score < 12:
            clarity_reason = score.evaluator_rationale.get(
                "clarity_score",
                "The question wording may be vague or underspecified."
            )
            clarity_reason = self._clean_sentence(clarity_reason)
            suggestion = self._suggest_action_for_clarity_issue(clarity_reason)
            return (
                ValidationStatus.REVIEW,
                f"Needs review: clarity score is low ({score.clarity_score:.0f}/20). "
                f"Reason: {clarity_reason}. Suggested action: {suggestion}"
            )

        if score.easy_to_fix_items:
            issues = self._format_issues(score.easy_to_fix_items)
            suggestion = self._suggest_action_for_fixable_issues(score.easy_to_fix_items)
            return (
                ValidationStatus.REVIEW,
                f"Needs review: fixable issue found - {issues}. Suggested action: {suggestion}"
            )

        if score.ambiguity_flags:
            issues = self._format_issues(score.ambiguity_flags)
            suggestion = self._suggest_action_for_ambiguity(score.ambiguity_flags)
            return (
                ValidationStatus.REVIEW,
                f"Needs review: ambiguity remains - {issues}. Suggested action: {suggestion}"
            )

        if 60 <= score.final_score < 85:
            return (
                ValidationStatus.REVIEW,
                f"Needs review: final score is {score.final_score:.0f}/100, below the automatic verification threshold. "
                "Suggested action: strengthen the question by making the business purpose, metric, or comparison dimension more explicit."
            )

        return (
            ValidationStatus.VERIFIED,
            f"Verified: final score is {score.final_score:.0f}/100 with strong grounding, clarity, and business relevance."
        )

    def _format_issues(self, issues: List[str], max_items: int = 3) -> str:
        cleaned = [self._clean_sentence(item) for item in issues[:max_items] if str(item).strip()]
        return "; ".join(cleaned)

    def _clean_sentence(self, text: str) -> str:
        return str(text).strip().rstrip(".")

    def _suggest_action_for_deal_breakers(self, issues: List[str]) -> str:
        issue_text = " ".join(issues).lower()
        suggestions = []

        if "metric" in issue_text:
            suggestions.append(
                "map the question to a metric in the metric registry or add a new metric definition before promotion."
            )

        if "dimension" in issue_text:
            suggestions.append(
                "use a dimension that exists in the semantic layer or include the missing dimension in field setup."
            )

        if "empty" in issue_text or "not answerable" in issue_text:
            suggestions.append(
                "rewrite the question so it can be answered from the available dataset and semantic layer."
            )

        if not suggestions:
            suggestions.append(
                "resolve the blocking issue before the question can be added to the verified library."
            )

        return self._dedupe_join(suggestions)

    def _suggest_action_for_clarity_issue(self, clarity_reason: str) -> str:
        reason = clarity_reason.lower()
        suggestions = []

        if "time" in reason or "grain" in reason or "period" in reason:
            suggestions.append(
                "add a clear time context, such as last 30 days, last month, current quarter, or over time."
            )

        if "metric" in reason:
            suggestions.append(
                "map the wording to a registered business metric or rewrite the metric phrase more explicitly."
            )

        if "dimension" in reason or "breakdown" in reason or "comparison" in reason:
            suggestions.append(
                "add a clear business dimension, such as site, region, team, shift, cohort, or tenure band."
            )

        if "generic" in reason or "vague" in reason:
            suggestions.append(
                "make the analytical intent more specific, such as trend, breakdown, comparison, top performers, or lowest performers."
            )

        if not suggestions:
            suggestions.append(
                "revise the wording so the metric, dimension, and analytical intent are clear enough for a verified question."
            )

        return self._dedupe_join(suggestions)

    def _suggest_action_for_fixable_issues(self, issues: List[str]) -> str:
        issue_text = " ".join(issues).lower()
        suggestions = []

        if "time" in issue_text or "grain" in issue_text or "period" in issue_text:
            suggestions.append(
                "add a clear time context, such as last 30 days, last month, last week, current quarter, or over time."
            )

        if "metric is not mapped" in issue_text or "registered business metric" in issue_text:
            suggestions.append(
                "map the metric phrase to an existing metric in the metric registry, or add a new metric definition."
            )

        if "dimension" in issue_text and "date field" not in issue_text:
            suggestions.append(
                "add a clear business dimension, such as site, region, team, shift, cohort, or tenure band."
            )

        if "date field" in issue_text:
            suggestions.append(
                "use the date field for trend analysis or filtering instead of treating it as a regular comparison dimension."
            )

        if "vague" in issue_text or "generic" in issue_text:
            suggestions.append(
                "rewrite the question with a more specific analytical intent, such as trend, breakdown, comparison, top performers, or lowest performers."
            )

        if not suggestions:
            suggestions.append(
                "review the listed issue and revise the question before promoting it to the verified library."
            )

        return self._dedupe_join(suggestions)

    def _suggest_action_for_ambiguity(self, issues: List[str]) -> str:
        issue_text = " ".join(issues).lower()
        suggestions = []

        if "time" in issue_text or "period" in issue_text:
            suggestions.append(
                "clarify the intended time range, such as last week, last month, or current quarter."
            )

        if "aggregation" in issue_text:
            suggestions.append(
                "specify the intended aggregation, such as average, total, rate, or count."
            )

        if "metric" in issue_text:
            suggestions.append(
                "clarify which registered metric the question should use."
            )

        if "business" in issue_text or "entity" in issue_text:
            suggestions.append(
                "clarify the business entity, such as site, team, manager, shift, cohort, or tenure band."
            )

        if not suggestions:
            suggestions.append(
                "clarify the ambiguous term before promoting this question to the verified library."
            )

        return self._dedupe_join(suggestions)

    def _dedupe_join(self, suggestions: List[str]) -> str:
        unique_suggestions = []
        for suggestion in suggestions:
            cleaned = self._clean_sentence(suggestion)
            if cleaned and cleaned not in unique_suggestions:
                unique_suggestions.append(cleaned)

        return " ".join(f"{item}." for item in unique_suggestions)