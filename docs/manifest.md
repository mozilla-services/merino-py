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
      "icon": "chrome://activity-stream/content/data/content/tippytop/images/google-com@2x.png"
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
