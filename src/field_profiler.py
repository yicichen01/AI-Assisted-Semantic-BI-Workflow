"""
Field profiling and semantic analysis utility.

Responsibilities:
- Analyze data field characteristics (type, distribution, cardinality)
- Generate semantic descriptions for fields
- Support field mapping to business concepts
"""

from typing import List
import pandas as pd
from .schemas import FieldProfile

class FieldProfiler:
    """Profiles data fields for semantic understanding."""

    def __init__(self):
        pass

    def profile_dataframe(self, df: pd.DataFrame, sample_size: int = 5) -> List[FieldProfile]:
        """
        Profile all columns in a pandas DataFrame.

        Args:
            df: pandas DataFrame
            sample_size: Number of sample values to include

        Returns:
            List of FieldProfile objects
        """
        profiles = []
        for col in df.columns:
            series = df[col]
            field_name = col
            dtype = str(series.dtype)
            total = len(series)
            null_count = series.isnull().sum()
            null_rate = float(null_count) / total if total > 0 else 0.0
            distinct_count = series.nunique(dropna=True)
            # Handle empty columns
            if total == 0:
                sample_values = []
            else:
                # Dropna, convert to string, get unique, sample
                sample_values = (
                    series.dropna().astype(str).unique().tolist()[:sample_size]
                )
            heuristic_role = self._guess_role(field_name, dtype, series)
            profiles.append(FieldProfile(
                field_name=field_name,
                dtype=dtype,
                null_rate=null_rate,
                distinct_count=int(distinct_count),
                sample_values=sample_values,
                heuristic_role=heuristic_role
            ))
        return profiles

    def _guess_role(self, field_name: str, dtype: str, series: pd.Series) -> str:
        """
        Guess the semantic role of a field based on name, dtype, and values.
        """
        import pandas as pd
        name_lower = field_name.lower()
        tokens = name_lower.split("_")

        # --- ID detection ---
        if name_lower == "id" or name_lower.endswith("_id") or (len(tokens) > 1 and tokens[-1] == "id"):
            return "id"

        # --- Date/time detection ---
        if pd.api.types.is_datetime64_any_dtype(series):
            return "date"
        if "date" in name_lower or "time" in name_lower:
            return "date"
        if self._is_date_like_string(series):
            return "date"

        # --- Flag (binary) detection ---
        non_null = series.dropna()
        unique_vals = set(str(v).strip().lower() for v in non_null.unique())
        flag_values = {"0", "1", "true", "false", "yes", "no"}
        if 1 <= len(unique_vals) <= 2 and unique_vals <= flag_values:
            return "flag"
        if pd.api.types.is_numeric_dtype(series):
            numeric_vals = set(non_null.unique())
            if numeric_vals <= {0, 1} and len(numeric_vals) > 0:
                return "flag"

        # --- Measure (numeric) detection ---
        if pd.api.types.is_numeric_dtype(series):
            # Exclude IDs
            if not (name_lower == "id" or name_lower.endswith("_id") or (len(tokens) > 1 and tokens[-1] == "id")):
                return "measure"

        # --- Dimension (categorical) detection ---
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_categorical_dtype(series):
            return "dimension"

        # Fallback
        return "dimension"

    def _is_date_like_string(self, series, sample_size: int = 10) -> bool:
        """
        Heuristic: sample a few non-null string values and try to parse as dates.
        Return True if most samples parse successfully.
        """
        non_null = series.dropna().astype(str)
        if non_null.empty:
            return False
        sample = non_null.sample(min(sample_size, len(non_null)), random_state=42)
        parsed = sample.apply(lambda x: self._safe_parse_date(x))
        success_rate = parsed.sum() / len(sample)
        return success_rate > 0.7

    @staticmethod
    def _safe_parse_date(val):
        import pandas as pd
        try:
            pd.to_datetime(val, errors="raise")
            return True
        except Exception:
            return False
