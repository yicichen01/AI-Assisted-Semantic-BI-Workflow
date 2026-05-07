from src.schemas import QuestionScore, ValidationStatus
from src.promotion_rules import PromotionRules


score = QuestionScore(
    grounding_score=20.0,
    relevance_score=20.0,
    clarity_score=20.0,
    complexity_score=18.0,
    format_score=20.0,
    final_score=98.0,
    deal_breakers=[],
    easy_to_fix_items=["Date field used as a regular dimension."],
    ambiguity_flags=[],
    evaluator_rationale={
        "grounding_score": "All metrics and dimensions are grounded.",
        "relevance_score": "Metric is relevant.",
        "clarity_score": "Question is clear.",
        "complexity_score": "Good analytical complexity.",
        "format_score": "Time grain specified."
    },
    validation_status=ValidationStatus.VERIFIED
)

rules = PromotionRules()
status, reason = rules.apply(score)

print("Final promotion status:", status)
print("Reason:", reason)