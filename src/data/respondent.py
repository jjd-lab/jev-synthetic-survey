"""Respondent data model"""


# Columns a preprocessor may add to carry per-respondent QUESTION TEXT (Qualtrics "piped
# text"), as opposed to per-respondent answers. Only Twin-2K-500's pricing block needs it:
# its price is randomized per respondent, so the shared stem in the question mapping holds
# a `{stem_value}` token instead of a price. See src/data/preprocessors/twin2k.py.
# Surveys whose preprocessor adds no such column get an empty dict, which makes the
# substitution in `_fill_stem` a no-op for them.
_STEM_PREFIX = "__stem__"


class Respondent:
    """Single respondent with demographics, screener profile, and ground truth"""

    def __init__(self, row_data: dict, question_mapper):
        """Initialize respondent from Excel row data

        Args:
            row_data: Dictionary from Excel row (column names as keys)
            question_mapper: QuestionMapper instance for decoding responses
        """
        # Try multiple possible ID column names (respid, "Response ID", ...)
        self.respid = row_data.get(
            "respid",
            row_data.get("repid",
            row_data.get("responseid",
            row_data.get("Response ID", "unknown"))))
        self.response_id = row_data.get(
            "responseid",
            row_data.get("response_id",
            row_data.get("Response ID", self.respid)))

        # Keep repid as alias for backward compatibility
        self.repid = self.respid

        # Explicit demographics (extracted from specific screener questions)
        # Example: {age: "35-44", income: "$75k-$100k", family_type: "Young family"}
        self.demographics = question_mapper.extract_demographics(row_data)

        # Screener profile (non-demographic questions)
        # Example: {S4: {question: "...", answer: "..."}, S5: {...}, ...}
        self.screener_profile = question_mapper.extract_screener_profile(row_data)

        # Ground truth responses
        # Single choice: {MU1: "Premium Package"}
        # Multi choice: {MU2: ["Dining plan", "Character experiences"]}
        self.ground_truth = question_mapper.extract_ground_truth(row_data)

        # Per-respondent question text: {QID9_1: "8.45", ...}. Empty for every survey whose
        # preprocessor adds no `__stem__` column. NaN is filtered by string rather than with
        # `pd.isna` to keep this model free of a pandas import; the values are short strings
        # written by the preprocessor, so "nan" cannot be a real one.
        self.stem_values = {
            key[len(_STEM_PREFIX):]: str(value).strip()
            for key, value in row_data.items()
            if isinstance(key, str)
            and key.startswith(_STEM_PREFIX)
            and str(value).strip().lower() not in ("", "nan", "none")
        }

        # Which arm of each between-subject condition group this respondent was randomized
        # into: {"__condition__Disease": "gain", ...}. Empty for every survey whose questions
        # declare no `condition_group`, which makes the router's arm gate inert for them.
        try:
            self.condition_assignments = question_mapper.condition_assignments(self.ground_truth)
        except ValueError as e:
            raise ValueError(f"respondent {self.respid}: {e}") from e

    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "respid": self.respid,
            "response_id": self.response_id,
            "demographics": self.demographics,
            "screener_profile": self.screener_profile,
            "ground_truth": self.ground_truth,
            "stem_values": self.stem_values,
            "condition_assignments": self.condition_assignments
        }

    def __repr__(self) -> str:
        return f"Respondent(respid={self.respid}, demographics={self.demographics}, screeners={len(self.screener_profile)}, ground_truth={len(self.ground_truth)})"
