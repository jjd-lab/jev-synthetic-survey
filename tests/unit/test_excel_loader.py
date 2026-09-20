"""Unit tests for excel_loader."""

import pytest

from src.data import ExcelSurveyLoader


@pytest.mark.unit
class TestExcelLoader:
    def test_load_minimal_fixture(self, minimal_excel_path, question_mapper):
        loader = ExcelSurveyLoader(minimal_excel_path, question_mapper)
        respondents = loader.load_respondents()
        assert len(respondents) == 2
        assert respondents[0].demographics

    def test_max_rows(self, minimal_excel_path, question_mapper):
        loader = ExcelSurveyLoader(minimal_excel_path, question_mapper)
        respondents = loader.load_respondents(max_rows=1)
        assert len(respondents) == 1

    def test_cp1252_apostrophe_decodes_cleanly(self, question_mapper, tmp_path):
        """Windows-1252 curly apostrophe (byte 0x92) must survive as a real apostrophe,
        not mojibake — the source CSV is cp1252, not utf-8."""
        csv_path = tmp_path / "cp1252.csv"
        # U+2019 RIGHT SINGLE QUOTATION MARK encodes to a single byte 0x92 in cp1252,
        # which is invalid utf-8 -> forces the fallback path.
        csv_path.write_bytes("col\nBachelor’s degree\n".encode("cp1252"))

        loader = ExcelSurveyLoader(str(csv_path), question_mapper)
        df = loader.load_data()
        value = str(df["col"].iloc[0])
        assert "�" not in value  # no replacement char
        assert value == "Bachelor’s degree"
