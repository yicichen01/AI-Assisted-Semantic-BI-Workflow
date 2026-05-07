from src.schemas import FieldSuggestion, QuestionCandidate
from src.question_scoring import QuestionScorer


field_suggestions = [
    FieldSuggestion(
        field_name="utilization_rate",
        include=True,
        friendly_name="Utilization Rate",
        synonyms=["capacity usage", "workload ratio"],
        field_role="measure",
        default_aggregation="avg",
        disallowed_aggregations=["sum"],
        format=None,
        confidence=0.9,
        rationale="Rate metric."
    ),
    FieldSuggestion(
        field_name="site",
        include=True,
        friendly_name="Site",
        synonyms=["location"],
        field_role="dimension",
        default_aggregation=None,
        disallowed_aggregations=["sum", "avg"],
        format=None,
        confidence=0.8,
        rationale="Business dimension."
    ),
    FieldSuggestion(
        field_name="record_date",
        include=True,
        friendly_name="Record Date",
        synonyms=["date"],
        field_role="date",
        default_aggregation=None,
        disallowed_aggregations=["sum", "avg"],
        format="yyyy-mm-dd",
        confidence=0.8,
        rationale="Date field."
    ),
]

metric_registry = {
    "utilization_rate": {
        "description": "Average utilization rate across sites and time periods.",
        "dependent_fields": ["utilization_rate"],
        "preferred_aggregation": "avg"
    }
}

candidate = QuestionCandidate(
    question_text="How did utilization rate trend by site last month?",
    target_metrics=["utilization_rate"],
    target_dimensions=["site", "record_date"],
    filters={},
    time_grain="month"
)

scorer = QuestionScorer()

score = scorer.score(
    candidate=candidate,
    metric_registry=metric_registry,
    glossary={},
    field_suggestions=field_suggestions
)

print(score)
print("Final score:", score.final_score)
print("Status:", score.validation_status)
print("Deal breakers:", score.deal_breakers)
print("Easy-to-fix:", score.easy_to_fix_items)
print("Ambiguity flags:", score.ambiguity_flags)