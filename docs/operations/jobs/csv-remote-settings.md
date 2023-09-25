# Merino Jobs Operations

## CSV Remote Settings Uploader Job

The CSV remote settings uploader is a job that uploads suggestions data in a CSV
file to remote settings. It takes two inputs:

1. A CSV file. The first row in the file is assumed to be a header that names
  the fields (columns) in the data.
2. A Python module that validates the CSV contents and describes how to convert
  it into suggestions JSON.

If you're uploading suggestions from a Google sheet, you can export a CSV file
from File > Download > Comma Separated Values (.csv). Make sure the first row in
the sheet is a header that names the columns.

### Uploading suggestions (Step by step)

If you're uploading a type of suggestion that the uploader already supports,
skip to [Running the uploader](#running-the-uploader) below. If you're not sure
whether it's supported, check in the `merino/jobs/csv_rs_uploader/` directory
for a file named similarly to the type.

To upload a new type of suggestion, follow the steps below. In summary, first
you'll create a Python module that implements a model for the suggestion type,
and then you'll run the uploader.

#### 1. Create a Python model module for the new suggestion type

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
on [Pydantic][Pydantic], which is used throughout Merino. `BaseSuggestion` is
implemented in `base.py`.

[Pydantic]: https://docs.pydantic.dev/latest/usage/models/

#### 3. Add suggestion fields to the class

Add a field to the class for each property that should appear in the output JSON
(except `score`, which the uploader will add automatically). Name each field as
you would like it to be named in the JSON. Give each field a type so that
Pydantic can validate it. For URL fields, use `HttpUrl` from the `pydantic`
module.

#### 4. Add validator methods to the class

Add a method annotated with Pydanyic's `@field_validator` decorator for each field.
Each validator method should transform its field's input value into an appropriate output value and raise a `ValueError` if the input value is invalid.
Pydantic will call these methods automatically as it performs validation.
Their return values will be used as the values in the output JSON.

`BaseSuggestion` implements two helpers you should use:

* `_validate_str()` - Validates a string value and returns the validated value.
  Leading and trailing whitespace is stripped, and all whitespace is replaced
  with spaces and collapsed. Returns the validated value.
* `_validate_keywords()` - The uploader assumes that lists of keywords are
  serialized in the input data as comma-delimited strings. This helper method
  takes a comma-delimited string and splits it into individual keyword strings.
  Each keyword is converted to lowercase, some non-ASCII characters are replaced
  with ASCII equivalents that users are more likely to type, leading and
  trailing whitespace is stripped, and all whitespace is replaced with spaces
  and collapsed. Returns the list of keyword strings.

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
  upload. It takes either a path to a CSV file or a `list[dict]` that will be
  used to create a file object (`StringIO`) for an in-memory CSV file. Prefer
  passing in a `list[dict]` instead of creating a file and passing a path, since
  it's simpler.
* `do_error_test()` - Makes sure a given error is raised when expected. Use
  `ValidationError` from the `pydantic` module to check validation errors and
  `MissingFieldError` from `merino.jobs.csv_rs_uploader` to check input CSV that
  is missing an expected field (column).

#### 7. Run the test

```
$ MERINO_ENV=testing poetry run pytest tests/unit/jobs/csv_rs_uploader/test_foo.py
```

See also the main Merino development documentation for running unit tests.

#### 8. Submit a PR

Once your test is passing, submit a PR with your changes so that the new
suggestion type is committed to the repo. This step isn't necessary to run the
uploader and upload your suggestions, so you can come back to it later.

#### 9. Upload!

See [Running the uploader](#running-the-uploader).

### Running the uploader

Run the following from the repo's root directory to see documentation for all
options and their defaults. Note that the `upload` command is the only command
in the `csv-rs-uploader` job.

```
poetry run merino-jobs csv-rs-uploader upload --help`
```

The uploader takes a CSV file as input, so you'll need to download or create one
first.

Here's an example that uploads suggestions in `foo.csv` to the remote settings
dev server:

```
poetry run merino-jobs csv-rs-uploader upload \
  --server "https://remote-settings-dev.allizom.org/v1" \
  --bucket main-workspace \
  --csv-path foo.csv \
  --model-name foo \
  --record-type foo-suggestions \
  --auth "Bearer ..."
```

Let's break down each command-line option in this example:

* `--server` - Suggestions will be uploaded to the remote settings dev server
* `--bucket` - The `main-workspace` bucket will be used
* `--csv-path` - The CSV input file is `foo.csv`
* `--model-name` - The model module is named `foo`. Its path within the repo
  would be `merino/jobs/csv_rs_uploader/foo.py`
* `--record-type` - The `type` in the remote settings records created for these
  suggestions will be set to `foo-suggestions`. This argument is optional and
  defaults to `"{model_name}-suggestions"`
* `--auth` - Your authentication header string from the server. To get a header,
  log in to the server dashboard (don't forget to log in to the Mozilla VPN
  first) and click the small clipboard icon near the top-right of the page,
  after the text that shows your username and server URL. The page will show a
  "Header copied to clipboard" toast notification if successful.

#### Setting suggestion scores

By default all uploaded suggestions will have a `score` property whose value is
defined in the `remote_settings` section of the Merino config. This default can
be overridden using `--score <number>`. The number should be a float between 0
and 1 inclusive.

#### Other useful options

* `--dry-run` - Log the output suggestions but don't upload them. The uploader
  will still authenticate with the server, so `--auth` must still be given.

### Structure of the remote settings data

The uploader uses `merino/jobs/utils/chunked_rs_uploader.py` to upload the
output suggestions. In short, suggestions will be chunked, and each chunk will
have a corresponding remote settings record with an attachment. The record's ID
will be generated from the `--record-type` option, and its type will be set to
`--record-type` exactly. The attachment will contain a JSON array of suggestion
objects in the chunk.
