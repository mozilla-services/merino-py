# Merino Jobs Operations

## Geonames Uploader Job

The geonames uploader is a job that uploads geographical place data from
[geonames.org](https://www.geonames.org/) to remote settings. This data is used
by the Suggest client to recognize place names and relationships for certain
suggestion types like weather suggestions.

The job consists of a single command called `upload`. It uploads two types of
records:

* Core geonames data ([geonames](#geonames-records))
* Alternate names ([alternates](#alternates-records))

Core geonames data includes places' primary names, numeric IDs, their countries
and administrative divisions, geographic coordinates, population sizes, etc.
This data is derived from the main `geoname` table described in the [geonames
documentation](https://download.geonames.org/export/dump/readme.txt).

A single place and its data is referred to as a **geoname**.

Alternate names are the different names associated with a geoname. A single
geoname can have many alternate names since a place can have many different
variations of its name. For example, New York City can be referred to as "New
York City," "New York," "NYC," "NY", etc. Alternate names also include
translations of the geoname's name into different languages. In Spanish, New
York City is "Nueva York."

Alternate names are referred to simply as **alternates**.


### Usage

```
uv run merino-jobs geonames-uploader upload \
    --rs-server 'https://remote-settings-dev.allizom.org/v1' \
    --rs-bucket main-workspace \
    --rs-collection quicksuggest-other \
    --rs-auth 'Bearer ...'
```

This will upload data for the countries and client locales that are hardcoded by
the job.


### Geonames records

Each geonames record corresponds to a **partition** of geonames within a given
country. A partition has a lower population threshold and an optional upper
population threshold, and the geonames in the partition are the geonames in the
partition's country with population sizes that fall within that range. The lower
threshold is inclusive and the upper threshold is exclusive.

If a partition has an upper threshold, its record's attachment contains its
country's geonames with populations in the range [lower, upper), and the
record's ID is `geonames-{country}-{lower}-{upper}`.

If a partition does not have an upper threshold, its attachment contains
geonames with populations in the range [lower, infinity), and the record's ID is
`geonames-{country}-{lower}`.

`country` is an [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2)
code like `US`, `GB`, and `CA`. `lower` and `upper` are in thousands and
zero-padded to four places.

A partition can have a list of **client countries**, which are are added to its
record's filter expression so that only clients in those countries will ingest
the partition's record.

Partitions serve a couple of purposes. First, they help keep geonames attachment
sizes small. Second, they give us control over the clients that ingest a set of
geonames. For example, we might want clients outside a country to ingest only
its large, well known geonames, while clients within the country should ingest
its smaller geonames.

If there are no geonames with population sizes in a partition's range, no record
will be created for the partition.

#### Types of geonames

Three types of geonames can be included in each attachment: cities,
administrative divisions, and countries. Administrative divisions correspond to
things like states, provinces, territories, and boroughs. A geoname can have up
to four administrative divisions, and the meaning and number of divisions
depends on the country and can even vary within a country.

#### Example geonames record IDs

* `geonames-US-0050-0100`
  * US geonames with populations in the range [50k, 100k)
* `geonames-US-1000`
  * US geonames with populations in the range [1m, infinity)


### Alternates records

Each alternates record corresponds to a single geonames record and language.
Since a geonames record corresponds to a country and partition, that means each
alternates record corresponds to a country, partition, and language. The
alternates record contains alternates in the language for the geonames in the
geonames record.

The ID of an alternates record is the ID of its corresponding geonames record
with the language code appended:

* `geonames-{country}-{lower}-{upper}-{language}`
* `geonames-{country}-{lower}-{language}` (for geonames records without an upper
  threshold)

`language` is a language code as defined in the geonames alternates data. There
are generally three types of language codes in the data:

* A two-letter [ISO 639](https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes)
  language code, like `en`, `es`, `pt`, `de`, and `fr`
* A locale code combining an ISO 639 language code with an
  [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2) country
  code, like `en-GB`, `es-MX`, and `pt-BR`
* A geonames-specific pseudo-code:
  * `abbr` - Abbreviations, like "NYC" for New York City
  * `iata` - Airport codes, like "PDX" for Portland Oregon USA
  * Others that we generally don't use

The input to the geonames uploader job takes Firefox locale codes, and the job
automatically converts each locale code to a set of appropriate geonames
language codes. Alternates record IDs always include the geonames language code,
not the Firefox locale code (although sometimes they're the same).

If a geonames record includes client countries (or in other words has a filter
expression limiting ingest to clients in certain countries), the corresponding
alternates record for a given language will have a filter expression limiting
ingest to clients using a locale that is both valid for the language and
supported within the country.

If a geonames record does not include any client countries, then the
corresponding alternates record will have a filter expression limiting ingest to
clients using a locale that is valid for the language.

The supported locales of each country are defined in
[`CONFIGS_BY_COUNTRY`](#country-and-locale-selection).

Alternates records for the `abbr` (abbreviations) and `iata` (airport codes)
pseudo-language codes are automatically created for each geonames partition,
when `abbr` and `iata` alternates exist for geonames in the parition.

#### Excluded alternates

The job may exclude selected alternates in certain cases, or in other words it
may not include some alternates you expect it to. To save space in remote
settings, alternates that are the same as a geoname's primary name or ASCII name
are usually excluded.

Also, it's often the case that a partition does not have any alternates at all,
or any alternates in a given language.

#### Example alternates record IDs

* `geonames-US-0050-0100-en`
  * English-language alternates for US geonames with populations in the range
    [50k, 100k)
* `geonames-US-0050-0100-en-GB`
  * British-English-language alternates for US geonames with populations in the
    range [1m, infinity)
* `geonames-US-1000-de`
  * German-language alternates for US geonames with populations in the range
    [1m, infinity)
* `geonames-US-1000-abbr`
  * Abbreviations for US geonames with populations in the range [1m, infinity)
* `geonames-US-1000-iata`
  * Airport codes for US geonames with populations in the range [1m, infinity)


### Country and locale selection

Because the geonames uploader is a complex job and typically uploads a lot of
data at once, it hardcodes the selection of countries and Firefox locales. This
means that, if you want to make any changes to the records that are uploaded,
you'll need to modify the code, but the tradeoff is that all supported countries
and locales are listed in one place, you don't need to run the job more than
once per upload, and there's no chance of making mistakes on the command line.

The job does not re-upload unchanged records by default.

The selection of countries and locales is defined in the `CONFIGS_BY_COUNTRY`
dict in the job's `__init__.py`. Here are example entries for Canada and the US:

```python
CONFIGS_BY_COUNTRY = {
    "CA": CountryConfig(
        geonames_partitions=[
            Partition(threshold=50_000, client_countries=["CA"]),
            Partition(threshold=250_000, client_countries=["CA", "US"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=EN_CLIENT_LOCALES + ["fr"],
    ),
    "US": CountryConfig(
        geonames_partitions=[
            Partition(threshold=50_000, client_countries=["US"]),
            Partition(threshold=250_000, client_countries=["CA", "US"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=EN_CLIENT_LOCALES,
    ),
}
```

Each entry maps an [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2)
country code to data for the country. The data includes two properties:

* `geonames_partitions` determines the geonames records that will be created for the country
* `supported_client_locales` contributes to the set of languages for which
  alternates records will be created, not only for the country but for all
  countries in `CONFIGS_BY_COUNTRY`

#### `geonames_partitions`

`geonames_partitions` is a list of one or more [partitions](#geonames-records).
Each partition defines its lower population threshold and client countries. The
upper threshold is automatically calculated from the partition with the
next-largest threshold.

Client countries should be defined for all partitions except possibly the last.
If the last partition doesn't include `client_countries`, its record won't have
a filter expression, so it will be ingested by all clients regardless of
country.

In the example `CONFIGS_BY_COUNTRY` above, US geonames will be partitioned into
three records:

* `geonames-US-0050-0100`
  * US geonames with populations in the range [50k, 100k) that will be ingested
    only by US clients. Its filter expression will be `env.country in ['US']`
* `geonames-US-0100-0500`
  * US geonames with populations in the range [100k, 500k) that will be ingested
    by US and Canadian clients. Its filter expression will be
    `env.country in ['CA', 'US']`
* `geonames-US-0500`
  * US geonames with populations in the range [500k, infinity) that will be
    ingested by all clients. It won't have a filter expression.

#### `supported_client_locales`

`supported_client_locales` is a list of Firefox locales. The job will convert
the locales to geonames alternates languages and create one alternates record
per geoname record per country per language (generally -- see the caveat about
[excluded alternates](#excluded-alternates)).

Note that `supported_client_locales` is not necessarily a list of all
conceivable locales for a country. It's only a list of locales that need to be
supported in the country. In the example `CONFIGS_BY_COUNTRY` above, the entry
for Canada includes both English and French locales. If you didn't need to
support Canadian clients using the `fr` locale, you could leave out `fr`. If you
did leave out `fr` but then added a `CONFIGS_BY_COUNTRY` entry for France, which
presumably would include support for the `fr` locale, then French-language
alternates for all countries in `CONFIGS_BY_COUNTRY` would be uploaded anyway,
and Canadian clients using the `fr` locale would ingest them even though `fr`
wasn't listed as a supported Canadian locale.

The example `CONFIGS_BY_COUNTRY` uses `EN_CLIENT_LOCALES`, which is all English
locales supported by Firefox: `en-CA`, `en-GB`, `en-US`, and `en-ZA`. Up to 15
alternates records will be created for the three US geonames records due to the
following math:

```
3 US geonames records * (
    `en` language
    + `en-CA` language
    + `en-GB` language
    + `en-US` language
    + `en-ZA` language
)
```

In reality, most of the US geonames records won't have geonames with alternates
in the `en-*` languages, only the `en` language, so it's more likely that only
the following alternates records will be created:

* `geonames-US-0050-0100-en`
  * `en` language alternates for the geonames in the `geonames-US-0050-0100`
    record. Its filter expression will be
    `env.locale in ['en-CA', 'en-GB', 'en-US', 'en-ZA']`
* `geonames-US-0100-0500-en`
  * `en` language alternates for the geonames in the `geonames-US-0100-0500`
    record. Its filter expression will be
    `env.locale in ['en-CA', 'en-GB', 'en-US', 'en-ZA']`
* `geonames-US-0500-en`
  * `en` language alternates for the geonames in the `geonames-US-0500` record.
    Its filter expression will be
    `env.locale in ['en-CA', 'en-GB', 'en-US', 'en-ZA']`
* Plus maybe one or two `en-GB` and/or `en-CA` records

### Operation

For each country in `CONFIGS_BY_COUNTRY`, the job performs two steps
corresponding to the two types of records:

Step 1:

1. Download the country's geonames from geonames.org
2. Upload the country's geonames records
3. Delete unused geonames records for the country

Step 2:

1. Download the country's alternates from geonames.org
2. For each alternates language, upload the country's alternates records
3. Delete unused alternates records for the country

The job does not re-create or re-upload records and attachments that haven't
changed.


### Command-line options

As with all Merino jobs, options can be defined in Merino's config files in
addition to being passed on the command line.

#### `--alternates-url-format`

Format string for alternates zip files on the geonames server. Should contain a
reference to a `country` variable. Default value:
`https://download.geonames.org/export/dump/alternatenames/{country}.zip`

#### `--force-reupload`

Recreate records and attachments even when they haven't changed.

#### `--geonames-url-format`

Format string for geonames zip files on the geonames server. Should contain a
reference to a `country` variable. Default value:
`https://download.geonames.org/export/dump/{country}.zip`

#### `--rs-dry-run`

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
    uv run merino-jobs geonames-uploader upload \
    --rs-server 'https://remote-settings-dev.allizom.org/v1' \
    --rs-bucket main-workspace \
    --rs-collection quicksuggest-other \
    --rs-auth 'Bearer ...' \
    --rs-dry-run
```

Look for "Uploading attachment" in the output.

You can make the log easier to read if you have [jq](https://jqlang.org/)
installed. Use the `mozlog` format and pipe the output to `jq ".Fields.msg"`
like this:

```
MERINO_LOGGING__LEVEL=INFO MERINO_LOGGING__FORMAT=mozlog \
    uv run merino-jobs geonames-uploader upload \
    --rs-server 'https://remote-settings-dev.allizom.org/v1' \
    --rs-bucket main-workspace \
    --rs-collection quicksuggest-other \
    --rs-auth 'Bearer ...' \
    --rs-dry-run \
    | jq ".Fields.msg"
```
