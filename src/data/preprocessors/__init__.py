"""Survey-specific raw-data preprocessors.

Each module exposes a ``preprocess(df, **params) -> df`` callable referenced by
dotted path from a survey config's ``data_source.preprocess`` block. Preprocessors
run in-memory between raw load and respondent build, so all survey-specific data
shaping lives here rather than in the shared loader/mapper.
"""
