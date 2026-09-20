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

    def test_skip_rows_drops_from_the_front(self, minimal_excel_path, question_mapper):
        loader = ExcelSurveyLoader(minimal_excel_path, question_mapper)
        both = loader.load_respondents()
        rest = ExcelSurveyLoader(minimal_excel_path, question_mapper).load_respondents(skip_rows=1)
        assert len(rest) == 1
        assert rest[0].respid == both[1].respid, "skip must drop the first row, not an arbitrary one"

    def test_skip_rows_defaults_to_a_no_op(self, minimal_excel_path, question_mapper):
        loader = ExcelSurveyLoader(minimal_excel_path, question_mapper)
        assert len(loader.load_respondents()) == 2

    def test_skip_rows_offsets_inside_the_max_rows_window(self, question_mapper, tmp_path):
        """`max_rows` names the window and `skip_rows` offsets into it, so the pair is an
        absolute slice of the file. Applied in the other order, `max_rows=5, skip_rows=2`
        would yield rows 3-7 instead of 3-5, and two runs meant to partition a panel would
        overlap."""
        csv_path = tmp_path / "rows.csv"
        csv_path.write_text("col\n" + "\n".join(str(i) for i in range(1, 11)) + "\n",
                            encoding="utf-8")

        loader = ExcelSurveyLoader(str(csv_path), question_mapper)
        df = loader.load_data(max_rows=5, skip_rows=2)

        assert list(df["col"]) == [3, 4, 5]

    def test_skip_rows_past_the_window_is_empty_not_wrapped(self, question_mapper, tmp_path):
        csv_path = tmp_path / "rows.csv"
        csv_path.write_text("col\n" + "\n".join(str(i) for i in range(1, 11)) + "\n",
                            encoding="utf-8")

        loader = ExcelSurveyLoader(str(csv_path), question_mapper)
        assert len(loader.load_data(max_rows=3, skip_rows=5)) == 0

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
