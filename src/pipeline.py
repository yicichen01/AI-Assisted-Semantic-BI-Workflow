"""
End-to-end orchestration layer for the Semantic BI Workflow.

Responsibilities:
- Run the full pipeline from field profiling to promotion decisions
- Coordinate semantic setup, candidate question generation, scoring, and validation
- Return structured workflow outputs for Streamlit display and downstream review
"""

from typing import Any, Dict, List

import pandas as pd

from src.field_profiler import FieldProfiler
from src.semantic_agent import SemanticAgent
from src.question_generator import QuestionGenerator
from src.question_scoring import QuestionScorer
from src.promotion_rules import PromotionRules


class BIWorkflowPipeline:
    """End-to-end orchestration layer for the BI semantic setup and question validation workflow."""

    def __init__(self) -> None:
        self.field_profiler = FieldProfiler()
        self.semantic_agent = SemanticAgent()
        self.question_generator = QuestionGenerator()
        self.question_scorer = QuestionScorer()
        self.promotion_rules = PromotionRules()

    def run(
        self,
        df: pd.DataFrame,
        metric_registry: Dict[str, Any],
        glossary: Dict[str, Any],
        seed_questions: List[str],
        max_questions: int = 20,
        llm_service: Any = None,
        domain_name: str = "",
    ) -> Dict[str, Any]:
        """Run the full BI workflow pipeline."""

        field_profiles = self.field_profiler.profile_dataframe(df)

        field_suggestions = self.semantic_agent.suggest_fields(
            field_profiles=field_profiles,
            metric_registry=metric_registry,
            glossary=glossary,
            seed_questions=seed_questions,
            llm_service=llm_service,
            domain_name=domain_name,
        )

        candidate_questions = self.question_generator.generate_candidates(
            field_suggestions=field_suggestions,
            metric_registry=metric_registry,
            glossary=glossary,
            seed_questions=seed_questions,
            max_questions=max_questions,
        )

        scored_questions = []
        promotion_results = []

        for candidate in candidate_questions:
            score = self.question_scorer.score(
                candidate=candidate,
                metric_registry=metric_registry,
                glossary=glossary,
                field_suggestions=field_suggestions,
            )

            promotion_status, promotion_reason, guardrail_category, suggested_fix = (
                self.promotion_rules.apply(score)
            )

            scored_questions.append(
                {
                    "candidate": candidate,
                    "score": score,
                }
            )

            promotion_results.append(
                {
                    "question_text": candidate.question_text,
                    "target_metrics": candidate.target_metrics,
                    "target_dimensions": candidate.target_dimensions,
                    "filters": candidate.filters,
                    "time_grain": candidate.time_grain,
                    "final_score": score.final_score,
                    "scoring_status": score.validation_status.value,
                    "promotion_status": promotion_status.value,
                    "promotion_reason": promotion_reason,
                    "guardrail_category": guardrail_category,
                    "suggested_fix": suggested_fix,
                    "deal_breakers": score.deal_breakers,
                    "easy_to_fix_items": score.easy_to_fix_items,
                    "ambiguity_flags": score.ambiguity_flags,
                    "evaluator_rationale": score.evaluator_rationale,
                }
            )

        return {
            "field_profiles": field_profiles,
            "field_suggestions": field_suggestions,
            "candidate_questions": candidate_questions,
            "scored_questions": scored_questions,
            "promotion_results": promotion_results,
        }
