# Working with the Manifest endpoint

## Overview

The `/manifest` endpoint returns a curated list of websites with associated metadata. This endpoint is designed to be used as part of your development process to maintain an up-to-date copy of website favicons.

## Endpoint details

- URL: `https://merino.services.mozilla.com/api/v1/manifest`
- Method: `GET`
- Response: `JSON`

```json
{
  "domains": [
    {
      "rank": 1,
      "domain": "google",
      "categories": [
        "Search Engines"
      ],
      "serp_categories": [
        0
      ],
      "url": "https://www.google.com/",
      "title": "Google",
      "icon": ""
    },
    {
      "rank": 2,
      "domain": "microsoft",
      "categories": [
        "Business",
        "Information Technology"
      ],
      "serp_categories": [
        0
      ],
      "url": "https://www.microsoft.com/",
      "title": "Microsoft – AI, Cloud, Productivity, Computing, Gaming & Apps",
      "icon": "https://merino-images.services.mozilla.com/favicons/90cdaf487716184e4034000935c605d1633926d348116d198f355a98b8c6cd21_17174.oct"
    }
  ]
}
```

The `icon` field has the url of the Mozilla-hosted favicon of the website.


## Usage

- You can save the JSON response as a `manifest.json` file:

```bash
curl https://merino.services.mozilla.com/api/v1/manifest -o manifest.json
```

Or, if you have [`jq`](https://jqlang.github.io/jq/) installed on your system, you can pretty-print it:

```bash
curl -s https://merino.services.mozilla.com/api/v1/manifest | jq '.' > manifest.json
```

- Check it into your repository and ship it with the application you are building.
- Whenever you need to display a favicon for a website or URL, you can check the `Manifest` file and use the `icon` field as a link to the favicon.

## Add custom domains

You are also able to add custom domains to this endpoint. We currently run a weekly cron job to collect favicons from the Top 2000 websites. Adding custom domains is handled via this Python file in the Merino codebase:
https://github.com/mozilla-services/merino-py/blob/main/merino/jobs/navigational_suggestions/custom_domains.py

To add yours:
1. `git clone git@github.com:mozilla-services/merino-py.git`
2. Add a new entry to the `CUSTOM_DOMAINS` list with `url` and at least one `category`: https://github.com/mozilla-services/merino-py/blob/main/merino/jobs/navigational_suggestions/custom_domains.py
3. Create a PR against the `merino-py` repo with your changes

The custom domains will be picked up during the next run (every Wednesday). This job can also be run manually by following instructions [here](https://github.com/mozilla-services/merino-py/blob/main/docs/operations/jobs/navigational_suggestions.md#running-the-job-in-airflow).

## Add custom favicons

Some websites block automated scrapers or have unreliable favicon detection. For these domains, you can specify a direct favicon URL that will be used instead of attempting to scrape it.

### What are custom favicons?

Custom favicons are pre-defined favicon URLs stored in `merino/jobs/navigational_suggestions/enrichments/custom_favicons.py`. When the job processes a domain, it checks this file **first** before attempting to scrape the favicon. This ensures reliable favicon delivery for domains that would otherwise fail.

### Where is this file used?

The `CUSTOM_FAVICONS` dictionary is imported and used by the domain processor (`processing/domain_processor.py`) during the favicon extraction phase. If a domain is found in the custom favicons mapping, the job will:
1. Download the specified favicon URL
2. Upload it to the CDN
3. Skip the web scraping step entirely for that domain's favicon

### Adding custom favicons with the CLI (Recommended)

The easiest way to add custom favicons is using the `probe-images` command-line tool. This tool will automatically test a domain, find the best favicon, and save it to the `CUSTOM_FAVICONS` dictionary.

**Basic usage:**

```bash
# Test a domain and save its best favicon
probe-images example.com --save
```

**With options:**

```bash
# Specify minimum favicon width (default is 32px)
probe-images example.com --save --min-width 64

# Test multiple domains at once
probe-images example.com mozilla.org github.com --save
```

**What the CLI does:**

When you run `probe-images` with the `--save` flag, it will:
1. Scrape the domain and extract all available favicons
2. Apply the same selection logic used in production to find the best favicon
3. Automatically update `merino/jobs/navigational_suggestions/enrichments/custom_favicons.py`
4. Add the domain (without TLD) as the key and the best favicon URL as the value

**Example output:**

```
Testing domain: mozilla.org
✅ Success!
 Title           Internet for people, not profit — Mozilla Global
 Best Icon       https://www.mozilla.org/media/img/favicons/mozilla/favicon-196x196.png
 Total Favicons  5

All favicons found:
- https://www.mozilla.org/media/img/favicons/mozilla/apple-touch-icon.png (rel=apple-touch-icon size=180x180)
- https://www.mozilla.org/media/img/favicons/mozilla/favicon-196x196.png (rel=icon size=196x196)
- https://www.mozilla.org/media/img/favicons/mozilla/favicon.ico (rel=shortcut,icon)

Save Results:
 Saved Domain  mozilla
 Saved URL     https://www.mozilla.org/media/img/favicons/mozilla/favicon-196x196.png
 Save PATH     merino/jobs/navigational_suggestions/enrichments/custom_favicons.py

Summary: 1/1 domains processed successfully
```

### Adding custom favicons manually

You can also manually edit the `CUSTOM_FAVICONS` dictionary if you already know the favicon URL:

1. `git clone git@github.com:mozilla-services/merino-py.git`
2. Edit `merino/jobs/navigational_suggestions/enrichments/custom_favicons.py`
3. Add a new entry to the `CUSTOM_FAVICONS` dictionary:

```python
CUSTOM_FAVICONS: dict[str, str] = {
    "axios": "https://static.axios.com/icons/favicon.svg",
    "espn": "https://a.espncdn.com/favicon.ico",
    "yoursite": "https://yoursite.com/path/to/favicon.png",  # Add your domain here
    # ...
}
```

**Important notes:**
- Use the second-level domain name **without** the TLD (e.g., use `"mozilla"` not `"mozilla.org"`)
- Use the direct URL to the favicon file
- Ensure the URL is publicly accessible and won't break over time

4. Create a PR against the `merino-py` repo with your changes

The custom favicons will be used during the next job run (every Wednesday), or can be triggered manually.
