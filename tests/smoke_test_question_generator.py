from src.schemas import FieldSuggestion
from src.question_generator import QuestionGenerator


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

generator = QuestionGenerator()

questions = generator.generate_candidates(
    field_suggestions=field_suggestions,
    metric_registry={},
    glossary={},
    seed_questions=[
        "How did utilization rate trend by site last month?",
        "Which site had the highest utilization rate?"
    ],
    max_questions=10
)

print(f"Generated {len(questions)} questions:\n")

for i, q in enumerate(questions, start=1):
    print(f"{i}. {q.question_text}")
    print(f"   Metrics: {q.target_metrics}")
    print(f"   Dimensions: {q.target_dimensions}")
    print(f"   Filters: {q.filters}")
    print(f"   Time grain: {q.time_grain}")
    print()