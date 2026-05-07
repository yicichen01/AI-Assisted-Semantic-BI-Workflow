import pandas as pd

from src.pipeline import BIWorkflowPipeline


df = pd.DataFrame(
    {
        "record_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "site": ["A", "B", "A"],
        "utilization_rate": [0.72, 0.81, 0.76],
        "employee_id": ["E001", "E002", "E003"],
        "is_late": [0, 1, 0],
    }
)

metric_registry = {
    "utilization_rate": {
        "description": "Average utilization rate across sites and time periods.",
        "dependent_fields": ["utilization_rate"],
        "preferred_aggregation": "avg",
    }
}

glossary = {
    "utilization_rate": ["capacity usage", "workload ratio"],
    "site": ["location", "facility"],
    "record_date": ["date", "business date"],
}

seed_questions = [
    "How did utilization rate trend by site last month?",
    "Which site had the highest utilization rate?",
]

pipeline = BIWorkflowPipeline()

results = pipeline.run(
    df=df,
    metric_registry=metric_registry,
    glossary=glossary,
    seed_questions=seed_questions,
    max_questions=10,
)

print("Field profiles:", len(results["field_profiles"]))
print("Field suggestions:", len(results["field_suggestions"]))
print("Candidate questions:", len(results["candidate_questions"]))
print("Promotion results:", len(results["promotion_results"]))

print("\nSample promotion results:")
for item in results["promotion_results"][:5]:
    print(item["promotion_status"], "|", item["final_score"], "|", item["question_text"])
    print("Reason:", item["promotion_reason"])
    print()