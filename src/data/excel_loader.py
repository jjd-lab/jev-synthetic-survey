"""Excel survey data loader"""

import importlib

import pandas as pd
from typing import Any, Callable, List, Optional
from .respondent import Respondent
from .question_mapper import QuestionMapper


def resolve_dotted_path(dotted_path: str) -> Callable:
    """Resolve a 'pkg.module.attr' string to the referenced callable."""
    module_path, attr_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


class ExcelSurveyLoader:
    """Load and parse Excel file with survey respondent data"""

    def __init__(self, excel_path: str, question_mapper: QuestionMapper,
                 preprocess: Optional[Any] = None):
        """Initialize loader

        Args:
            excel_path: Path to Excel file
            question_mapper: QuestionMapper instance for decoding responses
            preprocess: Optional PreprocessConfig (callable dotted path + params).
                When set, the raw DataFrame is passed through the callable
                (df -> df) before respondents are built. Omit for a no-op.
        """
        self.excel_path = excel_path
        self.question_mapper = question_mapper
        self.preprocess = preprocess
        self.df = None

    def load_data(self, sheet_name: Optional[str] = None, max_rows: Optional[int] = None) -> pd.DataFrame:
        """Load Excel or CSV file into DataFrame

        Args:
            sheet_name: Sheet name to load (default: first sheet) - ignored for CSV files
            max_rows: Maximum number of rows to load (default: all rows)

        Returns:
            pandas DataFrame
        """
        print(f"Loading data file: {self.excel_path}")

        # Check if CSV or Excel
        if self.excel_path.lower().endswith('.csv'):
            # Try UTF-8 first; fall back to cp1252 (Windows-1252) for Windows-authored
            # CSVs, whose curly apostrophes (byte 0x92) UTF-8 rejects and latin-1 would
            # mangle into mojibake (e.g. "Bachelor’s" -> "Bachelor�s"). latin-1 stays
            # as a last-resort catch-all.
            for encoding in ('utf-8', 'cp1252', 'latin-1'):
                try:
                    self.df = pd.read_csv(self.excel_path, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
        elif sheet_name:
            self.df = pd.read_excel(self.excel_path, sheet_name=sheet_name)
        else:
            self.df = pd.read_excel(self.excel_path)

        # Filter out empty rows (no Response ID)
        if "Response ID" in self.df.columns:
            original_count = len(self.df)
            self.df = self.df[self.df["Response ID"].notna() & (self.df["Response ID"] != "")]
            filtered_count = original_count - len(self.df)
            if filtered_count > 0:
                print(f"Filtered out {filtered_count} empty rows (no Response ID)")

        if max_rows:
            self.df = self.df.head(max_rows)
            print(f"Limited to first {max_rows} rows")

        print(f"Loaded {len(self.df)} rows, {len(self.df.columns)} columns")
        return self.df

    def get_respondents(self) -> List[Respondent]:
        """Convert DataFrame to list of Respondent objects

        Returns:
            List of Respondent objects
        """
        if self.df is None:
            raise ValueError("Must call load_data() first")

        respondents = []
        errors = 0

        for idx, row in self.df.iterrows():
            try:
                row_dict = row.to_dict()
                respondent = Respondent(row_dict, self.question_mapper)
                respondents.append(respondent)
            except Exception as e:
                print(f"Warning: Failed to parse row {idx}: {e}")
                errors += 1
                continue

        print(f"Successfully parsed {len(respondents)} respondents ({errors} errors)")
        return respondents

    def load_respondents(self, sheet_name: Optional[str] = None, max_rows: Optional[int] = None) -> List[Respondent]:
        """Convenience method: Load Excel and return Respondent objects

        Args:
            sheet_name: Sheet name to load (default: first sheet)
            max_rows: Maximum number of rows to load (default: all rows)

        Returns:
            List of Respondent objects
        """
        self.load_data(sheet_name=sheet_name, max_rows=max_rows)
        self._apply_preprocess()
        return self.get_respondents()

    def _apply_preprocess(self) -> None:
        """Run the configured raw-data preprocessor (df -> df), if any."""
        if self.preprocess is None:
            return
        fn = resolve_dotted_path(self.preprocess.callable)
        params = self.preprocess.params or {}
        print(f"Applying preprocessor: {self.preprocess.callable}")
        before_cols = len(self.df.columns)
        self.df = fn(self.df, **params)
        print(f"Preprocess complete: {before_cols} -> {len(self.df.columns)} columns")

    def summarize(self) -> dict:
        """Get summary statistics about the loaded data"""
        if self.df is None:
            raise ValueError("Must call load_data() first")

        screener_ids = (
            set(self.question_mapper.get_screener_questions())
            | set(self.question_mapper.get_demographic_questions())
        )
        response_ids = set(self.question_mapper.question_mapping.keys())

        screener_cols = [c for c in self.df.columns if c in screener_ids]
        response_cols = [c for c in self.df.columns if c in response_ids]

        return {
            "total_rows": len(self.df),
            "total_columns": len(self.df.columns),
            "screener_columns": len(screener_cols),
            "response_columns": len(response_cols),
            "columns": list(self.df.columns)
        }
