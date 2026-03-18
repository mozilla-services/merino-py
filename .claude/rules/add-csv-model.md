---
paths:
  - "merino/jobs/csv_rs_uploader/**"
  - "tests/**/csv_rs_uploader/**"
---

# How to Add a New CSV Uploader Model

For `merino-jobs csv-rs-uploader upload`:

1. Create `merino/jobs/csv_rs_uploader/mymodel.py`
2. Define `Suggestion` class extending `RowMajorBaseSuggestion` (one row = one suggestion) or `BaseSuggestion` (custom aggregation)
3. Implement `row_major_field_map()` returning `dict[str, str]` mapping CSV column names to model field names
4. Add `@field_validator` decorators for validation. Use `cls._validate_str()` and `cls._validate_keywords()` helpers from base.
5. Optionally override `default_collection()` for a non-default Remote Settings collection
6. Optionally override `csv_to_suggestions()` for custom filtering (see `fakespot.py` blocklist pattern)

Usage: `merino-jobs csv-rs-uploader upload --csv-path data.csv --model-name mymodel`

Reference models: `mdn.py` (simple), `pocket.py` (keyword validation), `fakespot.py` (blocklist filtering), `yelp.py` (complex fields)
