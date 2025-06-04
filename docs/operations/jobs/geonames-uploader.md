# Merino Jobs Operations

## Geonames Uploader Job

The geonames uploader is a job that uploads geographical place data from
[geonames.org](https://www.geonames.org/) to remote settings. This data is used
by the Suggest client to recognize place names and relationships for certain
suggestion types like weather suggestions.

The job consists of two commands:

* **`geonames-uploader geonames`** - Uploads core geonames data to remote settings
* **`geonames-uploader alternates`** - Uploads alternate names to remote settings

The core geonames data includes places' primary names, IDs, their countries and
administrative regions, geographic coordinates, populations, etc. This data is
derived from the main `geoname` table described in the
[geonames documentation](https://download.geonames.org/export/dump/readme.txt).

Alternate names are the different names associated with a place. A single
geoname can have many alternate names since a place can have many different
variations of its name. Alternate names can also include translations of the
geoname's name into different languages. Alternate names are usually referred to
simply as "alternates."

Typically both commands should be run when using this job, first `geonames` and
then `alternates`.


### Quick start

#### 1. Run the `geonames` command

```
uv run merino-jobs geonames-uploader geonames \
    --country US \
    --partitions '[[50, "US"], [100, ["US", "CA"]], 500]' \
    --rs-server 'https://remote-settings-dev.allizom.org/v1' \
    --rs-bucket main-workspace \
    --rs-collection quicksuggest-other \
    --rs-auth 'Bearer ...'
```

This will create three geonames records containing US geonames with the
following IDs:

* `geonames-US-50k-100k`
  * US geonames whose populations are in the range [50k, 100k) that will be
    ingested only by US clients
* `geonames-US-100k-500k`
  * US geonames whose populations are in the range [100k, 500k) that will be
  ingested by US and CA clients
* `geonames-US-500k`
  * US geonames whose populations are >= 500k that will be ingested by all
    clients

#### 2. Run the `alternates` command

```
uv run merino-jobs geonames-uploader alternates \
    --country US \
    --alternates-language en \
    --rs-server 'https://remote-settings-dev.allizom.org/v1' \
    --rs-bucket main-workspace \
    --rs-collection quicksuggest-other \
    --rs-auth 'Bearer ...'
```

This will create three English alternates records corresponding to the geonames
records in the previous step. They'll have the following IDs:

* `geonames-US-50k-100k-en`
  * `en` alternates for the geonames in the `geonames-US-50k-100k` record
* `geonames-US-100k-500k-en`
  * `en` alternates for the geonames in the `geonames-US-100k-500k` record
* `geonames-US-500k-en`
  * `en` alternates for the geonames in the `geonames-US-500k` record


### The `geonames` command

The `geonames` command downloads geonames for a given country from geonames.org,
partitions them by given population thresholds, uploads an RS record for each
partition, and deletes existing unused geonames records for the country.

Three types of geonames are downloaded: cities, administrative divisions, and
the geoname representing the country itself. Administrative divisions correspond
to things like states, provinces, territories, and boroughs. A geoname can have
up to four administrative divisions, and the meaning and number of divisions
depends on the country and can even vary within a country.

A list of one or more partitions should always be specified, typically on the
command line with `--partitions`. One geonames record per partition (per
country) will be created. Each partition defines a population threshold and any
number of filter-expression countries. If a partition does define any
filter-expression countries, its record will have a filter expression that limits
ingest only to clients in those countries. This allows clients outside a country
to ingest only its large, well known geonames, while clients within the country
can ingest its smaller geonames.

Geonames record IDs have the format `geonames-{lower}-{upper}`, where `lower` is
the partition's lower population threshold and `upper` is its upper threshold.
If a partition doesn't have an upper threshold, its record's ID will be
`geonames-{lower}`.

#### `geonames` command-line options

##### `--country code`

*Required.* The country whose geonames should be uploaded as an
[ISO-3166](https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes)
two-letter uppercase country code.

*Examples:*

* `--country US`
* `--country GB`
* `--country CA`

##### `--partitions json`

*Required.* A JSON string describing how the geonames should be partitioned. One
geonames record will be created per partition. Each partition defines a
population threshold and optionally one or more filter-expression countries. The
`json` value should be any one of the following:

* An integer population threshold
* A tuple `[threshold, country]`, where `threshold` is an integer population
  threshold and `country` is country code string
* A tuple `[threshold, countries]`, where `threshold` is an integer population
  threshold and `countries` is an array of country code strings
* An array whose items are any combination of the above

**Important: All integer population thresholds are in thousands**. For example,
a specified value of `50` means 50 thousand.

Each partition defines only its lower threshold. The upper threshold is
automatically calculated from the partition with the next-largest threshold. The
lower threshold is inclusive and the upper threshold is exclusive, or in other
words a partition's range is `[lower, upper)`.

The final partition -- that is, the partition with the largest threshold --
won't have an upper threshold.

*Examples:*

`--partitions 50`

* Creates one record with geonames whose populations are >= 50k that all clients
  will ingest

`--partitions '[50, "US"]'`

* Creates one record with geonames whose populations are >= 50k that only US
  clients will ingest

`--partitions '[[50, "US"], 100]'`

* Creates two records:
  * One with geonames whose populations are in the range [50k, 100k) that only
    US clients will ingest
  * One with geonames whose populations are >= 100k that all clients will ingest

`--partitions '[[50, "US"], [100, ["US", "CA", "GB"]], 500]'`

* Creates three records:
  * One with geonames whose populations are in the range [50k, 100k) that only
    US clients will ingest
  * One with geonames whose populations are in the range [100k, 500k) that US,
    CA, and GB clients will ingest
  * One with geonames whose populations are >= 500k that all clients will ingest

#### `geonames` example 1

```
uv run merino-jobs geonames-uploader geonames \
    --country US \
    --partitions '[1000]' \
    --rs-server 'https://remote-settings-dev.allizom.org/v1' \
    --rs-bucket main-workspace \
    --rs-collection quicksuggest-other \
    --rs-auth 'Bearer ...'
```

This will create one geonames record whose ID is `geonames-US-1m` containing US
geonames whose populations are at least 1 million. The record won't have a
filter expression, so it will be ingested by all clients.

#### `geonames` example 2

```
uv run merino-jobs geonames-uploader geonames \
    --country US \
    --partitions '[[500, "US"], 1000]' \
    --rs-server 'https://remote-settings-dev.allizom.org/v1' \
    --rs-bucket main-workspace \
    --rs-collection quicksuggest-other \
    --rs-auth 'Bearer ...'
```

This will create two geonames records containing US geonames with the following
IDs:

* `geonames-US-500k-1m`
  * US geonames whose populations are in the range [500k, 1m) that will have a
    filter expression `env.country in ['US']`
* `geonames-US-1m`
  * US geonames whose populations are >= 1 million that won't have a filter
    expression


### The `alternates` command

The `alternates` command should be run after the `geonames` command. For a given
country and language, it gets all the geonames records in remote settings for
that country, downloads those geonames' alternates from geonames.org, creates an
alternates record for each geonames record that contains alternates for the
language, and deletes existing unused alternates records for the country and
language. In summary, one alternates record per geonames record per language is
created.

The ID of an alternates record will be the ID of its corresponding geonames
record with the language code appended.

#### `alternates` command-line options

##### `--country code`

*Required.* The country whose alternates should be uploaded as an
[ISO-3166](https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes)
two-letter uppercase country code.

*Examples:*

* `--country US`
* `--country GB`
* `--country CA`

##### `--language code`

*Required.* The language of the alternates that should be uploaded. This can be
an [ISO 639](https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes)
two-letter language code or one of the pseudo-codes specific to geonames.org
like "abbr" for abbreviations. See the
[geonames documentation](https://download.geonames.org/export/dump/readme.txt)
for details. This value should always be lowercase.

We typically create alternates records for the following pseudo-codes:

* `abbr` - Abbreviations
* `iata` - Airport codes

Can be specified multiple times to upload multiple languages for a country.

*Examples:*

* `--language en`
* `--language de`
* `--language abbr`
* `--language iata`

#### `alternates` example

```
uv run merino-jobs geonames-uploader alternates \
    --country US \
    --alternates-language en \
    --rs-server 'https://remote-settings-dev.allizom.org/v1' \
    --rs-bucket main-workspace \
    --rs-collection quicksuggest-other \
    --rs-auth 'Bearer ...'
```


### Other command-line options

The following are supported by both the `geonames` and `alternates` commands. As
with all Merino jobs, they can be defined in Merino's config files in addition
to being passed on the command line.

#### `--dry-run`

Don't perform any mutable remote settings operations.

#### `--rs-auth auth`

Your authentication header string from the server. To get a header, log in to
the server dashboard (don't forget to log in to the Mozilla VPN first) and click
the small clipboard icon near the top-right of the page, after the text that
shows your username and server URL. The page will show a "Header copied to
clipboard" toast notification if successful.

#### `--rs-bucket bucket`

The remote settings bucket to upload to.

#### `--rs-collection collection`

The remote settings collection to upload to.

#### `--rs-server url`

The remote settings server to upload to.


### Tips

#### Use attachment sizes to help decide population thresholds

Attachment sizes for geonames and alternates records can be quite large since
this job makes it easy to select a large number of geonames. As you decide on
population thresholds, you can check potential attachment sizes without making
any modifications by using `--rs-dry-run` with a log level of `INFO` like this:

```
MERINO_LOGGING__LEVEL=INFO \
    uv run merino-jobs geonames-uploader geonames \
    --country US \
    --partitions '[[50, "US"], [100, ["CA", "US"]], 500]' \
    --rs-dry-run
```

Look for "Uploading attachment" in the output.

You can make the log easier to read if you have [jq](https://jqlang.org/)
installed. Use the `mozlog` format and pipe the output to `jq ".Fields.msg"`
like this:

```
MERINO_LOGGING__LEVEL=INFO MERINO_LOGGING__FORMAT=mozlog \
    uv run merino-jobs geonames-uploader geonames \
    --country US \
    --partitions '[[50, "US"], [100, ["CA", "US"]], 500]' \
    --rs-dry-run \
    | jq ".Fields.msg"
```
