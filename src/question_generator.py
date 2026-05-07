from typing import List, Dict, Any, Optional
from .schemas import FieldSuggestion, QuestionCandidate


class QuestionGenerator:
    """
    Generates candidate BI questions for a natural-language self-service BI workflow.
    Heuristic MVP version (no LLM calls).
    """

    def __init__(self):
        pass

    def generate_candidates(
        self,
        field_suggestions: List[FieldSuggestion],
        metric_registry: Dict[str, Any],
        glossary: Dict[str, List[str]],
        seed_questions: List[str],
        max_questions: int = 20
    ) -> List[QuestionCandidate]:
        """
        Generate realistic manager-style candidate questions.

        Seed questions are used only as style/context anchors.
        They should not be returned directly as generated candidates.
        """
        included_fields = [f for f in field_suggestions if f.include]

        metrics = self._get_candidate_metrics(included_fields)
        dimensions = self._get_candidate_dimensions(included_fields)
        date_fields = [f for f in included_fields if f.field_role == "date"]

        templates = self._build_question_templates(metrics, dimensions, date_fields)

        questions = []

        for tpl in templates:
            for metric in metrics:
                for dim in tpl.get("dimensions", [[]]):
                    for date in tpl.get("dates", [None]):
                        dimension_label = (
                            " and ".join(self._format_question_label(d) for d in dim)
                            if dim
                            else ""
                        )

                        qtext = tpl["template"].format(
                            metric=metric["name"],
                            metric_syn=metric["synonym"],
                            dimension=dimension_label,
                            date=date["name"] if date else ""
                        ).strip()

                        if not qtext:
                            continue

                        candidate = QuestionCandidate(
                            question_text=qtext,
                            target_metrics=[metric["name"]],
                            target_dimensions=dim if dim else [],
                            filters={},
                            time_grain=self._infer_time_grain(date["name"]) if date else None
                        )
                        questions.append(candidate)

        questions += self._build_comparison_questions(metrics, dimensions)

        deduped = self._dedupe_questions(
            questions=questions,
            seed_questions=seed_questions
        )

        return deduped[:max_questions]

    def _get_candidate_metrics(self, fields: List[FieldSuggestion]) -> List[Dict[str, str]]:
        """Return included measure fields as candidate metrics."""
        metrics = []

        for f in fields:
            if f.field_role == "measure":
                metrics.append(
                    {
                        "name": f.field_name,
                        "synonym": self._format_question_label(f.friendly_name or f.field_name),
                    }
                )

        return metrics

    def _get_candidate_dimensions(self, fields: List[FieldSuggestion]) -> List[str]:
        """
        Return regular business dimensions.

        Date fields and flags are intentionally excluded because they should not
        be used as regular top/bottom or comparison dimensions in the MVP generator.
        """
        dims = []

        for f in fields:
            if f.field_role == "dimension":
                dims.append(f.field_name)

        return dims

    def _build_question_templates(self, metrics, dimensions, date_fields):
        """Build reusable question templates without directly reusing seed questions."""
        templates = []

        # Trend questions: use date fields for time grain, but do not mention raw date column names.
        if date_fields:
            templates.append({
                "template": "How did {metric_syn} trend by {dimension} over time?",
                "dimensions": [[d] for d in dimensions],
                "dates": [{"name": df.field_name} for df in date_fields]
            })

        # Breakdown questions
        templates.append({
            "template": "Show {metric_syn} broken down by {dimension}.",
            "dimensions": [[d] for d in dimensions],
            "dates": [None]
        })

        # Top questions
        templates.append({
            "template": "Which {dimension} had the highest {metric_syn}?",
            "dimensions": [[d] for d in dimensions],
            "dates": [None]
        })

        # Bottom questions
        templates.append({
            "template": "Which {dimension} had the lowest {metric_syn}?",
            "dimensions": [[d] for d in dimensions],
            "dates": [None]
        })

        # Comparison questions
        templates.append({
            "template": "Compare {metric_syn} across {dimension}s.",
            "dimensions": [[d] for d in dimensions],
            "dates": [None]
        })

        return templates

    def _build_comparison_questions(self, metrics, dimensions):
        """Build more specific comparison/ranking questions."""
        questions = []

        if metrics and dimensions:
            for metric in metrics:
                for dim in dimensions:
                    dim_label = self._format_question_label(dim)
                    qtext = f"Compare {metric['synonym']} for top 3 {dim_label}s in the last month."

                    questions.append(
                        QuestionCandidate(
                            question_text=qtext,
                            target_metrics=[metric["name"]],
                            target_dimensions=[dim],
                            filters={"top_n": 3},
                            time_grain="month"
                        )
                    )

        return questions

    def _dedupe_questions(
        self,
        questions: List[QuestionCandidate],
        seed_questions: Optional[List[str]] = None
    ) -> List[QuestionCandidate]:
        """
        Deduplicate generated questions by normalized question text.

        Seed questions should guide style and business context, not be returned
        as generated candidates.
        """
        seed_questions = seed_questions or []
        seed_keys = {self._normalize_text(q) for q in seed_questions}

        seen = set()
        deduped = []

        for q in questions:
            normalized_text = self._normalize_text(q.question_text)

            # Do not return exact seed questions as generated candidates.
            if normalized_text in seed_keys:
                continue

            # For product UI, identical question text should appear only once,
            # even if internal metadata such as time_grain differs.
            if normalized_text in seen:
                continue

            seen.add(normalized_text)
            deduped.append(q)

        return deduped

    def _format_question_label(self, value: str) -> str:
        """
        Convert technical field or friendly names into natural question labels.

        Examples:
        - "Total Tasks" -> "total tasks"
        - "manager_name" -> "manager name"
        - "utilization_rate" -> "utilization rate"
        """
        if not value:
            return ""

        label = str(value).replace("_", " ").strip()
        label = " ".join(label.split())
        return label.lower()

    def _normalize_text(self, text: str) -> str:
        """Normalize question text for duplicate and seed-question matching."""
        import re

        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _infer_time_grain(self, date_field: Optional[str]) -> Optional[str]:
        if not date_field:
            return None

        name = date_field.lower()

        if any(grain in name for grain in ["month", "mon"]):
            return "month"
        if any(grain in name for grain in ["year", "yr"]):
            return "year"
        if any(grain in name for grain in ["week", "w"]):
            return "week"
        if any(grain in name for grain in ["day", "date"]):
            return "day"

        return None


"""
Optional LLM-based question generator placeholder for a later phase.

This is intentionally not used by the heuristic MVP pipeline.
"""


class LLMQuestionGenerator:
    """Generates BI questions from schema or context using an LLM in a later phase."""

    def __init__(self, model: str = "gpt-4"):
        self.model = model

    def generate(self, schema: dict, context: dict = None) -> list:
        """
        Placeholder for future LLM-based question generation.

        Args:
            schema: Data schema or semantic layer.
            context: Optional user or business context.

        Returns:
            List of generated questions.
        """
        # TODO: Implement optional LLM-based question generation logic in Phase 2.
        return []
