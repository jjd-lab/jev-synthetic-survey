"""Question mapping utilities for screener and response questions"""

import json
import math
import re
from typing import Dict, List, Any, Optional


def _normalize_choice_value(raw_value) -> str:
    """Convert Excel cell value to string choice key (e.g. 1.0 -> '1')."""
    if isinstance(raw_value, float) and raw_value.is_integer():
        return str(int(raw_value))
    return str(raw_value)


def _is_filled(raw_value) -> bool:
    """True if a cell holds a real (non-empty, non-NaN) value."""
    if raw_value is None:
        return False
    if isinstance(raw_value, float) and math.isnan(raw_value):
        return False
    text = str(raw_value).strip()
    return text != "" and text.lower() != "nan"


_QUALTRICS_SUFFIX_RE = re.compile(
    r"\s*\[(?:Skip|SKIP)\s+to\s+[^\]]+\]\s*$",
    re.IGNORECASE,
)

# Qualtrics piped-answer token, e.g. "[Q30A24C]" -> option Q30.A24 (the respondent's
# own "Other" free text piped as the answer). Groups: (question_num, option_num).
_PIPE_TOKEN_RE = re.compile(r"\[Q(\d+)A(\d+)C\]")

# Prefix for the between-subject arm assignments `condition_assignments` produces, seeded into
# the stateful runner's `state` so `QuestionRouter` can read them the same way it reads answers.
# Prefixed to keep them out of the question-id namespace: the router's "already answered" check
# and the per-question validation both key on real question ids.
CONDITION_PREFIX = "__condition__"


def _strip_qualtrics_suffix(text: str) -> str:
    """Remove Qualtrics routing suffixes like '[Skip to Q5]' from answer text."""
    return _QUALTRICS_SUFFIX_RE.sub("", text).strip()


_PUNCT_NORMALIZE_TABLE = str.maketrans({
    "\u2019": "'",  # right single quotation mark
    "\u2018": "'",  # left single quotation mark
    "\u201c": '"',  # left double quotation mark
    "\u201d": '"',  # right double quotation mark
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
})


def _normalize_punct(text: str) -> str:
    """Map common Unicode punctuation to ASCII equivalents for answer matching."""
    return text.translate(_PUNCT_NORMALIZE_TABLE)


def _canonicalize_single_answer(raw: str, config: dict) -> str:
    """Map raw CSV single-choice text to canonical option label from mapping."""
    text = _strip_qualtrics_suffix(str(raw).strip())
    choices = config.get("choices", {})
    if not choices:
        return text

    if text in choices.values():
        return text

    key = _normalize_choice_value(text)
    if key in choices:
        return choices[key]

    # Likert endpoints: CSV may store "1" while canonical label is "1=Not a fan at all"
    if key.isdigit():
        for choice_key, choice_text in choices.items():
            if choice_key == key:
                return choice_text
            if choice_text == key:
                return choice_text

    # Punctuation fallback: CSV may use curly quotes/dashes while config uses ASCII.
    norm_text = _normalize_punct(text)
    for choice_text in choices.values():
        if _normalize_punct(choice_text) == norm_text:
            return choice_text

    return text


_FAN_LEVEL_LABELS = {
    "1": "1=Not a fan at all",
    "2": "2=Slight fan",
    "3": "3=Moderate fan",
    "4": "4=Big fan",
    "5": "5=Very big fan",
}


def fan_level_label(raw_value) -> str:
    """Expand bare 1-5 fan ratings to labeled scale text (endpoints anchored)."""
    text = str(raw_value).strip()
    if not text or text.lower() == "nan":
        return text
    if "=" in text:
        return text
    key = _normalize_choice_value(text)
    return _FAN_LEVEL_LABELS.get(key, text)


def strip_dma_code(raw_value) -> str:
    """Remove trailing Nielsen DMA code, e.g. 'Miami-Ft. Lauderdale (528)' -> name only."""
    text = str(raw_value).strip()
    return re.sub(r"\s*\(\d+\)\s*$", "", text).strip()


def bucket_age_5yr(raw_value) -> str:
    """Map exact age to a non-overlapping band: "18-19", then 20-24, 25-29, ...

    The first band is 18-19 (survey minimum is 18); from 20 up, bands floor to 5-year
    boundaries. Avoids the old overlap where 18 -> "18-22" but 20 -> "20-24".
    """
    age = int(float(raw_value))
    if age < 20:
        return "18-19"
    lower = (age // 5) * 5
    return f"{lower}-{lower + 4}"


def bucket_age_standard(raw_value) -> str:
    """Map exact age to standard marketing bands: 18-24, 25-34, …, 65+."""
    age = int(float(raw_value))
    if age < 18:
        return "18-24"
    if age <= 24:
        return "18-24"
    if age <= 34:
        return "25-34"
    if age <= 44:
        return "35-44"
    if age <= 54:
        return "45-54"
    if age <= 64:
        return "55-64"
    return "65+"


def _apply_demographic_transform(value: str, transform: Optional[str]) -> str:
    """Apply optional post-processing to a demographic field value."""
    if transform == "bucket_5yr":
        return bucket_age_5yr(value)
    if transform == "bucket_standard":
        return bucket_age_standard(value)
    if transform == "fan_level_label":
        return fan_level_label(value)
    if transform == "strip_dma_code":
        return strip_dma_code(value)
    return value


class QuestionMapper:
    """Maps question IDs (S1, MU1, etc.) to question text and choices"""

    def __init__(self, demographic_mapping_path: str, question_mapping_path: str,
                 data_format: str = "coded"):
        """Initialize mapper with JSON mapping files

        Args:
            demographic_mapping_path: Path to demographic mapping JSON
            question_mapping_path: Path to survey question mapping JSON
            data_format: "coded" (numeric codes) or "text" (raw text, as Twin-2K-500 uses)
        """
        self.demographic_mapping = self._load_json(demographic_mapping_path)
        self.question_mapping = self._load_json(question_mapping_path)
        self.data_format = data_format
        self._column_cache: Dict[str, Optional[str]] = {}

    def _find_column_by_prefix(self, respondent_row: dict, qid: str) -> Optional[str]:
        """Find the CSV column whose name starts with the question id.

        Text-format columns are named "<qid>: <question text>" for single-choice
        and "<qid>.A<n>: <question text>" for multi-select. Matches on the qid
        token boundary (":" or ".") so "Q1" does not match "Q10".
        """
        if qid in self._column_cache:
            col = self._column_cache[qid]
            return col if col in respondent_row else None

        for col in respondent_row:
            if not isinstance(col, str):
                continue
            if col == qid or col.startswith(f"{qid}:") or col.startswith(f"{qid} "):
                self._column_cache[qid] = col
                return col
        self._column_cache[qid] = None
        return None

    def _load_json(self, path: str) -> dict:
        """Load JSON file with encoding fallback"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except UnicodeDecodeError:
            # Fallback to latin-1 if UTF-8 fails
            with open(path, 'r', encoding='latin-1') as f:
                return json.load(f)

    def get_demographic_questions(self) -> Dict[str, dict]:
        """Get all screener questions marked as demographic

        Returns:
            Dictionary of {question_id: config} for demographic questions
        """
        return {
            qid: config
            for qid, config in self.demographic_mapping.items()
            if config.get("type") == "demographic"
        }

    def get_screener_questions(self) -> Dict[str, dict]:
        """Get non-demographic screener questions

        Returns:
            Dictionary of {question_id: config} for screener questions
        """
        return {
            qid: config
            for qid, config in self.demographic_mapping.items()
            if config.get("type") == "screener"
        }

    def extract_demographics(self, respondent_row: dict) -> Dict[str, str]:
        """Extract demographics from respondent row

        Args:
            respondent_row: Dictionary with column names as keys (e.g., {S1: 2, S2: 4, ...})

        Returns:
            Dictionary of {demographic_key: choice_text}
            Example: {age: "35-44", income: "$75k-$100k", family_type: "Young family"}
        """
        demographics = {}

        for qid, config in self.get_demographic_questions().items():
            if qid not in respondent_row or respondent_row[qid] is None:
                continue

            demographic_key = config.get("demographic_key", qid)

            # Handle multi-select demographics (e.g., D2A children ages, D6 race/ethnicity)
            if config.get("is_multi_select", False):
                choice_columns = config.get("choices", {})
                selected_choices = []

                for col, choice_text in choice_columns.items():
                    if col in respondent_row and respondent_row[col] == 1:
                        selected_choices.append(choice_text)

                if selected_choices:
                    demographics[demographic_key] = ", ".join(selected_choices)
                continue

            # Handle text fields with no choices (e.g., Age, State, zipcode)
            if not config.get("choices"):
                if not _is_filled(respondent_row[qid]):
                    continue
                raw_text = str(respondent_row[qid]).strip()
                demographics[demographic_key] = _apply_demographic_transform(
                    raw_text, config.get("transform")
                )
                continue

            value = _normalize_choice_value(respondent_row[qid])
            choice_text = config["choices"].get(value)

            if choice_text is None:
                # Skip warning for empty string values
                if value and value != 'nan':
                    print(f"Warning: No choice mapping for {qid}={value}")
                continue

            demographics[demographic_key] = choice_text

        return demographics

    def extract_screener_profile(self, respondent_row: dict) -> Dict[str, dict]:
        """Extract non-demographic screener responses

        Args:
            respondent_row: Dictionary with column names as keys

        Returns:
            Dictionary of {question_id: {question: text, answer: text}}
            Example: {
                S4: {question: "Visit frequency?", answer: "Once every few years"},
                S5: {question: "Accommodation?", answer: "Moderate"}
            }
        """
        screener_profile = {}

        for qid, config in self.get_screener_questions().items():
            # Handle grid questions (e.g., S4, S5)
            if config.get("is_grid", False):
                items = config.get("items", {})
                scale = config.get("scale", {})
                responses = []

                for item_col, item_name in items.items():
                    if item_col in respondent_row and respondent_row[item_col] is not None:
                        value = str(respondent_row[item_col])
                        scale_text = scale.get(value, value)
                        responses.append(f"{item_name}: {scale_text}")

                if responses:
                    screener_profile[qid] = {
                        "question": config["question"],
                        "answer": "; ".join(responses)
                    }
                continue

            # Handle multi-select questions (e.g., S6, S6A)
            if config.get("is_multi_select", False):
                choices = config.get("choices", {})
                selected = []

                for col, choice_text in choices.items():
                    if col in respondent_row and respondent_row[col] == 1:
                        selected.append(choice_text)

                if selected:
                    screener_profile[qid] = {
                        "question": config["question"],
                        "answer": ", ".join(selected)
                    }
                continue

            # Handle free-text questions (essays, word associations, thought listings): there is
            # no option list to decode against, so render the cell as written -- the same case
            # extract_demographics handles for Age/State/zipcode above. Keyed on an explicit flag
            # rather than "choices is empty" because grid screeners also have empty
            # choices and must keep reaching the grid branch regardless of branch order.
            if config.get("free_text", False):
                if not _is_filled(respondent_row.get(qid)):
                    continue
                screener_profile[qid] = {
                    "question": config["question"],
                    # Normalize first so a numeric answer pandas read as 27.0 renders as "27"
                    "answer": _normalize_choice_value(respondent_row[qid]).strip()
                }
                continue

            # Handle standard single-choice questions
            if qid in respondent_row and respondent_row[qid] is not None:
                value = _normalize_choice_value(respondent_row[qid])
                choice_text = config["choices"].get(value)

                if choice_text is None:
                    if value and value != 'nan':
                        print(f"Warning: No choice mapping for {qid}={value}")
                    continue

                screener_profile[qid] = {
                    "question": config["question"],
                    "answer": choice_text
                }

        return screener_profile

    def extract_ground_truth(self, respondent_row: dict) -> Dict[str, Any]:
        """Extract ground truth responses from respondent row

        Args:
            respondent_row: Dictionary with column names as keys

        Returns:
            Dictionary of {question_id: response}
            For single choice: {MU1: "Premium Package"}
            For multi choice: {MU2: ["Dining plan", "Character experiences"]}
        """
        if self.data_format == "text":
            return self._extract_ground_truth_text(respondent_row)

        ground_truth = {}

        for qid, config in self.question_mapping.items():
            question_type = config.get("type", "single")

            if question_type == "single":
                # Single choice: MU1 column contains choice number
                # Support optional source_column for questions that pull from demographic columns
                source_col = config.get("source_column", qid)

                if source_col in respondent_row and respondent_row[source_col] is not None:
                    value = _normalize_choice_value(respondent_row[source_col])
                    choice_text = config["choices"].get(value)

                    if choice_text:
                        ground_truth[qid] = choice_text
                    else:
                        print(f"Warning: No choice mapping for {qid}={value} (source: {source_col})")

            elif question_type == "multi":
                # Multi choice: Multiple indicator columns (MU2_choice1, MU2_choice2, etc.)
                # Use choices.keys() directly (dict order preserved in Python 3.7+)
                choices_dict = config.get("choices", {})
                choice_columns = list(choices_dict.keys())
                selected_choices = []

                for col in choice_columns:
                    if col in respondent_row and respondent_row[col] == 1:
                        choice_text = choices_dict.get(col)
                        if choice_text:
                            selected_choices.append(choice_text)

                if selected_choices:
                    ground_truth[qid] = selected_choices

        return ground_truth

    def _extract_ground_truth_text(self, respondent_row: dict) -> Dict[str, Any]:
        """Extract ground truth when answers are stored as raw text.

        - Single-choice: column "<qid>: ..." holds the answer text directly.
        - Multi-select: each choice column (key in choices dict) holds the option
          text or is empty/NaN; collect the canonical choice text for filled cells.
        """
        ground_truth: Dict[str, Any] = {}

        for qid, config in self.question_mapping.items():
            question_type = config.get("type", "single")

            if question_type == "single":
                # Grid items carry an explicit CSV column (e.g. "Unnamed: 205"); plain
                # single questions resolve their column by "<qid>: ..." prefix.
                explicit_col = config.get("column")
                col = explicit_col if explicit_col is not None else \
                    self._find_column_by_prefix(respondent_row, qid)
                if col is None or col not in respondent_row:
                    continue
                raw = respondent_row[col]
                if _is_filled(raw):
                    ground_truth[qid] = _canonicalize_single_answer(raw, config)

            elif question_type == "multi":
                choices_dict = config.get("choices", {})
                selected_choices = []
                for col, choice_text in choices_dict.items():
                    if col in respondent_row and _is_filled(respondent_row[col]):
                        # Canonical option text keeps ground truth aligned with the
                        # option list used for masking/validation.
                        selected_choices.append(choice_text)

                if selected_choices:
                    ground_truth[qid] = selected_choices

            elif question_type == "open_ended":
                col = self._find_column_by_prefix(respondent_row, qid)
                if col is None:
                    continue
                raw = respondent_row[col]
                if _is_filled(raw):
                    ground_truth[qid] = str(raw).strip()

        # Open-end companion fields (e.g. Q30.A24.OE) used for piping
        for col, raw in respondent_row.items():
            if not isinstance(col, str) or ".OE" not in col:
                continue
            oe_key = col.split(":")[0].strip()
            if _is_filled(raw):
                ground_truth[oe_key] = str(raw).strip()

        # Resolve piped-answer tokens: a single-choice GT of "[Q30A24C]" means the
        # respondent picked their own "Other" text from Q30.A24 as the answer. Replace
        # the token with the resolved OE text (fall back to the placeholder label).
        for qid, answer in list(ground_truth.items()):
            if not isinstance(answer, str):
                continue
            token = _PIPE_TOKEN_RE.fullmatch(answer.strip())
            if not token:
                continue
            oe_key = f"Q{token.group(1)}.A{token.group(2)}.OE"
            resolved = ground_truth.get(oe_key)
            if not resolved:
                resolved = self.get_option_text_by_key(f"Q{token.group(1)}.A{token.group(2)}")
            if resolved:
                ground_truth[qid] = resolved

        return ground_truth

    def _get_response_config(self, question_id: str) -> Optional[dict]:
        return self.question_mapping.get(question_id)

    def get_question_text(self, question_id: str) -> str:
        """Get question text for a response question

        Args:
            question_id: Question ID (e.g., MU1, MU2)

        Returns:
            Question text string
        """
        config = self._get_response_config(question_id)
        return config.get("question", "") if config else ""

    def get_choices(self, question_id: str) -> Dict[str, str]:
        """Get choices for a response question

        Args:
            question_id: Question ID (e.g., MU1, MU2)

        Returns:
            Dictionary of {choice_id: choice_text}
        """
        config = self._get_response_config(question_id)
        return config.get("choices", {}) if config else {}

    def get_choice_options_list(self, question_id: str) -> List[str]:
        """Get ordered list of choice texts for a question

        Args:
            question_id: Question ID

        Returns:
            List of choice text strings in order
        """
        choices_dict = self.get_choices(question_id)
        config = self._get_response_config(question_id)

        if not config:
            return list(choices_dict.values())

        question_type = config.get("type", "single")

        if question_type == "single":
            sorted_choices = sorted(choices_dict.items(), key=lambda x: int(x[0]))
            return [choice_text for _, choice_text in sorted_choices]

        if question_type == "multi":
            # Use choices.keys() directly (dict order preserved in Python 3.7+)
            choice_columns = list(choices_dict.keys())
            return [choices_dict.get(col, "") for col in choice_columns if col in choices_dict]

        return list(choices_dict.values())

    def get_question_type(self, question_id: str) -> str:
        """Get question type (single or multi)

        Args:
            question_id: Question ID

        Returns:
            "single" or "multi"
        """
        config = self._get_response_config(question_id)
        return config.get("type", "single") if config else "single"

    def validate_question_types(self, questions: List[dict]) -> None:
        """Raise ValueError if YAML question types disagree with response mapping JSON."""
        for q in questions:
            qid = q.id if hasattr(q, "id") else q["id"]
            yaml_type = q.type if hasattr(q, "type") else q["type"]
            json_type = self.get_question_type(qid)
            if yaml_type != json_type:
                raise ValueError(
                    f"Question type mismatch for {qid}: "
                    f"config YAML has '{yaml_type}' but response_mapping.json has '{json_type}'"
                )

    def get_option_text_by_key(self, option_key: str) -> Optional[str]:
        """Resolve an option key like "Q30.A24" to its choice text ("Some other genre ...").

        Used for piping: the piped OE's parent option (Q30.A24) is the placeholder option
        text that a downstream question (Q31) shows and that should be replaced by the
        generated free text.
        """
        parent = option_key.split(".A")[0]
        config = self._get_response_config(parent)
        if not config:
            return None
        for col, text in config.get("choices", {}).items():
            if col == option_key or col.startswith(f"{option_key}:") or col.startswith(f"{option_key} "):
                return text
        return None

    def get_question_framing(self, question_id: str) -> str:
        """Return the answer framing for a question: "personal" (default) or "societal".

        Societal/prediction questions (e.g. Q23: "In 5 years, will most people…?") ask
        about society, not the respondent's own situation. The prompt injects different
        guidance per framing. Uniform within a grid (read from any member).
        """
        config = self._get_response_config(question_id)
        return config.get("framing", "personal") if config else "personal"

    def get_oe_field(self, question_id: str) -> Optional[str]:
        """Return the open-end companion column for a question (e.g. "Q30.A24.OE"), else None.

        Present on questions carrying an "Other, please specify" option. The LLM fills
        `other_text` when it picks that option; the runner stores it under this key for
        piping (e.g. Q31 pipes Q30.A24.OE).
        """
        config = self._get_response_config(question_id)
        return config.get("oe_field") if config else None

    def get_other_option_text(self, question_id: str) -> Optional[str]:
        """Return the canonical label of the "Other" option (e.g. "Some other genre ...")."""
        config = self._get_response_config(question_id)
        return config.get("other_option_text") if config else None

    def get_grid_group(self, question_id: str) -> Optional[str]:
        """Return the grid group id for a grid-item question (e.g. "Q24"), else None.

        Grid questions are expanded at config-generation time into per-item single
        questions, each tagged with `grid_group`. The stateful runner uses this to
        issue ONE combined LLM call per grid and fan the ratings back to per-item keys.
        """
        config = self._get_response_config(question_id)
        return config.get("grid_group") if config else None

    def get_grid_label(self, question_id: str) -> str:
        """Return the per-item label for a grid item (e.g. "Inflation"), else the qid."""
        config = self._get_response_config(question_id)
        return config.get("grid_label", question_id) if config else question_id

    def get_condition_group(self, question_id: str) -> Optional[str]:
        """Return the between-subject condition group for a question (e.g. "Disease"), else None.

        Questions in a condition group exist in two or more mutually exclusive arms; each
        respondent was randomized into exactly one. `QuestionRouter.is_asked` uses this to
        show a persona only its assigned arm. `None` for every ordinary question, which is
        what makes the gate inert for surveys with no between-subject design.
        """
        config = self._get_response_config(question_id)
        return config.get("condition_group") if config else None

    def get_condition_arm(self, question_id: str) -> Optional[str]:
        """Return which arm of its condition group this question belongs to (e.g. "gain")."""
        config = self._get_response_config(question_id)
        return config.get("condition_arm") if config else None

    def condition_assignments(self, ground_truth: Dict[str, Any]) -> Dict[str, str]:
        """Derive {CONDITION_PREFIX + group: arm} from which arm a respondent's answers fill.

        Presence *is* the randomization record: Qualtrics showed each respondent one arm, so
        only that arm's columns are filled. Only presence is read, never answer content — the
        gate must not become a channel for the human's actual answer.

        Raises when a group has zero or two-plus arms present. Twin-2K-500 measures exactly one
        arm per respondent for all 13 groups (asserted at config-generation time), so a
        violation here means the mapping's `condition_arm` tags disagree with the data.
        """
        arms_seen: Dict[str, set] = {}
        for qid in ground_truth:
            group = self.get_condition_group(qid)
            if group is None:
                continue
            arms_seen.setdefault(group, set()).add(self.get_condition_arm(qid))

        # Groups the mapping declares but this respondent filled no arm of.
        for config in self.question_mapping.values():
            group = config.get("condition_group")
            if group is not None:
                arms_seen.setdefault(group, set())

        assignments = {}
        for group, arms in sorted(arms_seen.items()):
            if len(arms) != 1:
                raise ValueError(
                    f"condition group '{group}' has {len(arms)} arm(s) answered "
                    f"({sorted(a for a in arms if a is not None) or 'none'}); each respondent "
                    f"must have been randomized into exactly one"
                )
            assignments[CONDITION_PREFIX + group] = arms.pop()
        return assignments

    def get_ordered_scale(self, question_id: str) -> bool:
        """Check if question has ordered scale (shouldn't randomize options)

        Args:
            question_id: Question ID

        Returns:
            True if options are ordered (Likert scale, etc.), False otherwise
        """
        config = self._get_response_config(question_id)
        return config.get("ordered_scale", False) if config else False

    def get_shuffle_options(self, question_id: str) -> bool:
        """Return whether this question's options should be shuffled in the prompt.

        Explicit per-question opt-in via ``shuffle_options`` in the mapping JSON.
        Absent or false => no shuffle (default off).
        """
        config = self._get_response_config(question_id)
        return bool(config.get("shuffle_options", False)) if config else False

    def get_anchor_options(self, question_id: str) -> List[str]:
        """Option strings pinned to the end of the shuffled list (in listed order).

        Anchors are options that must not float into a random middle position — "None of
        the above", "Other, please specify", "Don't Know". Explicit per-question config via
        ``anchor_options`` rather than a text heuristic, because substantive options also
        contain the word "other" (e.g. Q7's "smart glasses (Meta's, Rayban or other)").
        """
        config = self._get_response_config(question_id)
        return list(config.get("anchor_options", [])) if config else []
