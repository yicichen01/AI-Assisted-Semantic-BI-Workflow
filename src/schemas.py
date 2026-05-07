"""
Shared Pydantic schemas for the Semantic BI Workflow.

Responsibilities:
- Define typed data contracts across pipeline modules
- Standardize field profiles, semantic suggestions, candidate questions, and scoring outputs
- Support structured validation for heuristic agents and future LLM-based modules
- Keep workflow outputs consistent for Streamlit display and downstream review
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Union
from enum import Enum
class ValidationStatus(str, Enum):
    """Status for question validation."""
    VERIFIED = "verified"
    REVIEW = "review"
    REJECT = "reject"

class FieldProfile(BaseModel):
    """Profile of a BI field."""
    field_name: str
    dtype: str
    null_rate: float
    distinct_count: int
    sample_values: List[str]
    heuristic_role: str


class FieldSuggestion(BaseModel):
    """Suggestion for BI field inclusion and role."""
    field_name: str
    include: bool
    friendly_name: str
    synonyms: List[str]
    field_role: str
    default_aggregation: Optional[str] = None
    disallowed_aggregations: List[str]
    format: Optional[str] = None
    confidence: float
    rationale: str


class QuestionCandidate(BaseModel):
    """Candidate BI question with targets and filters."""
    question_text: str
    target_metrics: List[str]
    target_dimensions: List[str]
    filters: Dict[str, Union[str, int, float, List[str], List[int], List[float]]]
    time_grain: Optional[str] = None


class QuestionScore(BaseModel):
    """Scoring breakdown for a candidate question."""
    grounding_score: float
    relevance_score: float
    clarity_score: float
    complexity_score: float
    format_score: float
    final_score: float
    deal_breakers: List[str]
    easy_to_fix_items: List[str]
    ambiguity_flags: List[str]
    evaluator_rationale: Dict[str, str]
    validation_status: ValidationStatus


class ScoredQuestion(BaseModel):
    """A candidate question with its evaluation score."""
    candidate: QuestionCandidate
    score: QuestionScore
