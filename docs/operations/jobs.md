# Merino Jobs Operations

## Dynamic Wikipedia

Merino currently builds the Elasticsearch indexing job that runs in Airflow.
Airflow takes the `latest` image built as the base image.
The reasons to keep the job code close to the application code are:

1. Data models can be shared between the indexing job and application more easily. 
   This means that data migrations will be simpler.
2. All the logic regarding Merino functionality can be found in one place.
3. Eliminates unintended differences in functionality due to dependency mismatch.

### Where to find and modify the jobs

The job is configured in [`telemetry-airflow`](https://github.com/mozilla/telemetry-airflow).

You can access the job in the 
[Airflow Console](https://workflow.telemetry.mozilla.org/dags/merino_jobs/grid?search=merino_jobs).

## CSV remote settings uploader

The CSV remote settings uploader is a job that uploads suggestions data in a CSV
file to remote settings. It takes two inputs:

* A CSV file. The first row in the file is assumed to be a header that names
  the fields (columns) in the data.
* A Python module that validates the CSV contents and describes how to convert
  it into suggestions JSON.

If you're uploading suggestions from a Google sheet, you can export a CSV file
from File > Download > Comma Separated Values (.csv).

### Uploading a new type of suggestion

To upload a new type of suggestion, follow these steps:

#### 1. Create a Python model module

Add a Python module to `merino/jobs/csv_rs_uploader/`. It's probably easiest to
copy an existing model module like `mdn.py`, follow along with the steps here,
and modify it for the new suggestion type. Name the file according to the
suggestion type.

This file will define the model of the new suggestion type as it will be
serialized in the output JSON, perform validation and conversion of the input
data in the CSV, and define how the input data should map to the output JSON.

#### 2. Add the `Suggestion` class

In the module, implement a class called `Suggestion` that derives from
`BaseSuggestion` in `merino.jobs.csv_rs_uploader.base`. This class will be the
model of the new suggestion type. `BaseSuggestion` itself derives from
Pydantic's `BaseModel`, so the validation the class will perform will be based
on [Pydantic](), which is used throughout Merino. (`BaseSuggestion` is
implemented in `base.py`.)

[Pydantic]: https://docs.pydantic.dev/latest/usage/models/

#### 3. Add suggestion fields to the class

Add a field to the class for each property that should appear in the output JSON
(except `score`, which the uploader will add automatically). Name each field as
you would like it to be named in the JSON. Give each field a type so that
Pydantic can validate it. For URL fields, use `HttpUrl` from the `pydantic`
module.

#### 4. Add validator methods to the class

Add a method annotated with `@validator` for each field. Each validator method
should transform its field's input value into an appropriate output value and
raise a `ValueError` if the input value is invalid. Pydantic will call these
methods automatically as it performs validation. Their return values will be
used as the values in the output JSON.

`BaseSuggestion` implements two helpers you should use:

* `_validate_str()` - Validates a string value and returns the validated value.
Leading and trailing whitespace is stripped, and all whitespace is replaced with
spaces and collapsed. Returns the validated value.
* `_validate_keywords()` - The uploader assumes that lists of keywords are
serialized in the input data as comma-delimited strings. This helper method
takes a comma-delimited string and splits it into individual keyword strings.
Each keyword is converted to lowercase, some non-ASCII characters are replaced
with ASCII equivalents that users are more likely to type, leading and trailing
whitespace is stripped, and all whitespace is replaced with spaces and
collapsed. Returns the list of keyword strings.

#### 5. Implement the `csv_to_json()` class method

Add a `@classmethod` to `Suggestion` called `csv_to_json()`. It should return a
`dict` that maps from field (column) names in the input CSV to property names in
the output JSON.

#### 6. Add a test

Add a test file to `tests/unit/jobs/csv_rs_uploader/`. See `test_mdn.py` as an
example. The test should perform a successful upload as well as uploads that
fail due to validation errors and missing fields (columns) in the input CSV.

`utils.py` in the same directory implements helpers that your test should use:

* `do_csv_test()` - Makes sure the uploader works correctly during a successful
upload. It takes either a path to a CSV file or a `list[dict]` that will be used
to create a file object (`StringIO`) for an in-memory CSV file. Prefer passing
in a `list[dict]` instead of creating a file and passing a path, since it's
simpler.
* `do_error_test()` - Makes sure a given error is raised when expected. Use
`ValidationError` from `pydantic` to check validation errors and
`MissingFieldError` from `merino.jobs.csv_rs_uploader` to check input CSV that
is missing an expected field (column).

For information on running the test, see below.

### Running the uploader

```
$ poetry run merino-jobs csv-rs-uploader upload --server "https://remote-settings-dev.allizom.org/v1" --bucket main-workspace --csv-path foo.csv --model-name foo --record-type foo-suggestions --auth "Bearer ..."
```

Let's break down each command-line option in the example above:

* `--server` - Suggestions will be uploaded to the remote settings dev server
* `--bucket` - The `main-workspace` bucket will be used
* `--csv-path` - The CSV input file is `foo.csv`
* `--model-basename` - The model module is named `foo`. Its path within the repo
  would be `merino/jobs/csv_rs_uploader/foo.py`
* `--record-type` - The `type` in the remote settings records created for these
  suggestions will be set to `foo-suggestions`. This argument is optional and
  defaults to `"{model_name}-suggestions"`
* `--auth` - The user's authorization token from the server

#### Setting suggestion scores

By default all uploaded suggestions will have a `score` property whose value is
defined in the `remote_settings` section of the Merino config. This default can
be overridden using `--score <number>`. The number should be a float between 0
and 1 inclusive.

#### Other useful options

Some other useful options are documented below. To see all options, run:
`poetry run merino-jobs csv-rs-uploader upload --help`

* `--dry-run` - Log the generated output suggestions but don't upload them. The
  uploader will still authenticate with the server, so `--auth` must still be
  used.

### Running an uploader test

```
$ MERINO_ENV=testing poetry run pytest tests/unit/jobs/csv_rs_uploader/test_foo.py
```

See also the main Merino documentation for running unit tests.
