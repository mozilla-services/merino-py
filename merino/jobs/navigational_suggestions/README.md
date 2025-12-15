# Navigational Suggestions Job

## Overview

The Navigational Suggestions job extracts metadata (favicons and titles) from top domains and uploads them to Google Cloud Storage. This data powers Firefox's address bar suggestions feature.

The job processes ~2000 domains from BigQuery, supplements them with custom domains, attempts to fetch high-quality favicons, and produces a manifest file (`top_picks.json`) containing domain metadata.

## Quick Start

### Running Locally (Development Mode)

The fastest way to run the job locally:

```bash
# Ensure Docker is running
docker info

# Run the job with default settings (20 domains)
make nav-suggestions
```

The Makefile target automatically:
- Starts the fake-gcs-server Docker container
- Processes domains from `enrichments/custom_domains.py`
- Saves results to `./local_data/`
- Stops the container when finished

**View results:**
```bash
cat ./local_data/top_picks_latest.json
```

**Customize the run:**
```bash
# Process more domains
make nav-suggestions SAMPLE_SIZE=50

# Enable system monitoring
make nav-suggestions ENABLE_MONITORING=true

# Use custom output directory
make nav-suggestions METRICS_DIR=./my_output
```

### Running in Production Mode

Production mode requires Google Cloud credentials and BigQuery access:

```bash
merino-jobs navigational-suggestions prepare-domain-metadata \
  --src-gcp-project=<project> \
  --dst-gcp-project=<project> \
  --dst-gcs-bucket=<bucket> \
  --dst-cdn-hostname=<cdn>
```

## High-Level Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 1: DOMAIN COLLECTION                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
┌─────────────────┐        ┌──────────────────┐        ┌──────────────────┐
│   BigQuery      │        │ Custom Domains   │        │   Enrichments    │
│                 │        │                  │        │                  │
│ io/domain_data_ │        │ enrichments/     │        │ enrichments/     │
│ downloader.py   │        │ custom_domains   │        │ custom_favicons  │
│                 │        │                  │        │ partner_favicons │
│ Tranco rankings │        │ Curated list     │        │ Favicon overrides│
│ ~2000 domains   │        │ Additional sites │        │ Partner URLs     │
└─────────────────┘        └──────────────────┘        └──────────────────┘
         │                            │                            │
         └────────────────────────────┼────────────────────────────┘
                                      ▼
                           ┌──────────────────┐
                           │ Domain List      │
                           │ rank, categories │
                           │ domain, suffix   │
                           └──────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PHASE 2: DOMAIN PROCESSING LOOP                        │
│                     processing/domain_processor.py                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                           ┌──────────────────┐
                           │ Custom Favicon?  │◄────── enrichments/
                           │ Check mapping    │        custom_favicons.py
                           └──────────────────┘
                              │              │
                          YES │              │ NO
                              ▼              ▼
                    ┌──────────────┐   ┌──────────────────┐
                    │ Download &   │   │  Web Scraping    │
                    │ Upload       │   │                  │
                    │              │   │ scrapers/        │
                    │ io/async_    │   │ web_scraper.py   │
                    │ favicon_     │   │                  │
                    │ downloader   │   │ MechanicalSoup   │
                    └──────────────┘   │ Firefox UA       │
                          │            │ 15s timeout      │
                          │            └──────────────────┘
                          │                     │
                          │                     ▼
                          │            ┌──────────────────┐
                          │            │ Extract Favicons │
                          │            │                  │
                          │            │ favicon/         │
                          │            │ favicon_         │
                          │            │ extractor.py     │
                          │            │                  │
                          │            │ scrapers/        │
                          │            │ favicon_         │
                          │            │ scraper.py       │
                          │            └──────────────────┘
                          │                     │
                          │                     ▼
                          │         ┌────────────────────────┐
                          │         │ Favicon Sources:       │
                          │         │ 1. <link> tags      ■■■│  Priority 1
                          │         │ 2. <meta> tags      ■■ │  Priority 2
                          │         │ 3. /favicon.ico     ■  │  Priority 4
                          │         │ 4. manifest.json    ■  │  Priority 3
                          │         │ (max 5 icons)          │
                          │         └────────────────────────┘
                          │                     │
                          │                     ▼
                          │         ┌────────────────────────┐
                          │         │ Download Favicons      │
                          │         │                        │
                          │         │ io/async_favicon_      │
                          │         │ downloader.py          │
                          │         │                        │
                          │         │ Concurrent (batch=5)   │
                          │         └────────────────────────┘
                          │                     │
                          │                     ▼
                          │         ┌────────────────────────┐
                          │         │ Process & Select Best  │
                          │         │                        │
                          │         │ favicon/               │
                          │         │ favicon_processor.py   │
                          │         │                        │
                          │         │ Phase A: SVG first     │
                          │         │ Phase B: Bitmaps       │
                          │         └────────────────────────┘
                          │                     │
                          │                     ▼
                          │         ┌────────────────────────┐
                          │         │ Selection Rules        │
                          │         │                        │
                          │         │ favicon/               │
                          │         │ favicon_selector.py    │
                          │         │                        │
                          │         │ 1. Source priority     │
                          │         │ 2. Dimensions          │
                          │         │ 3. Min width (48px)    │
                          │         └────────────────────────┘
                          │                     │
                          └─────────────────────┤
                                                ▼
                                    ┌────────────────────────┐
                                    │ Upload to GCS          │
                                    │                        │
                                    │ io/domain_metadata_    │
                                    │ uploader.py            │
                                    │                        │
                                    │ SHA-256 hash           │
                                    │ favicons/{hash}_{size} │
                                    └────────────────────────┘
                                                │
                                    ┌───────────┴───────────┐
                                    │                       │
                                    ▼                       ▼
                          ┌──────────────────┐   ┌──────────────────┐
                          │ Extract Title    │   │ CDN URL          │
                          │                  │   │ https://cdn...   │
                          │ scrapers/        │   └──────────────────┘
                          │ web_scraper.py   │
                          │                  │
                          │ validators.py    │
                          │ (reject errors)  │
                          └──────────────────┘
                                    │
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PHASE 3: MANIFEST CONSTRUCTION                        │
│                     processing/manifest_builder.py                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │                                │
                    ▼                                ▼
         ┌──────────────────┐            ┌──────────────────┐
         │ Top Picks        │            │ Partner Manifest │
         │                  │            │                  │
         │ {                │            │ enrichments/     │
         │   domains: [     │            │ partner_         │
         │     rank,        │            │ favicons.py      │
         │     domain,      │            │                  │
         │     url,         │            │ Download & map   │
         │     title,       │            │ original → GCS   │
         │     icon,        │            └──────────────────┘
         │     categories   │                     │
         │   ]              │                     │
         │ }                │                     │
         └──────────────────┘                     │
                    │                             │
                    └───────────────┬─────────────┘
                                    ▼
                           ┌──────────────────┐
                           │ Merge Manifests  │
                           │{domains,partners}│
                           └──────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 4: DIFF & UPLOAD                              │
│                  io/domain_metadata_uploader.py                             │
│                  io/domain_metadata_diff.py                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │                                │
                    ▼                                ▼
         ┌──────────────────┐            ┌──────────────────┐
         │ Compare with     │            │ Upload to GCS    │
         │ Previous Version │            │                  │
         │                  │            │ {timestamp}_     │
         │ Calculate diff:  │            │ top_picks.json   │
         │ - Unchanged      │            │                  │
         │ - Added domains  │            │ top_picks_       │
         │ - Added URLs     │            │ latest.json      │
         └──────────────────┘            └──────────────────┘
                    │                                │
                    └───────────────┬────────────────┘
                                    ▼
                           ┌──────────────────┐
                           │   ✓ Complete     │
                           │                  │
                           │ Output available │
                           │ in GCS bucket    │
                           └──────────────────┘


EXECUTION MODES:
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────┐        ┌─────────────────────────────┐
│      NORMAL MODE            │        │      LOCAL MODE             │
│  (modes/normal_mode.py)     │        │(modes/local_mode_runner.py) │
├─────────────────────────────┤        ├─────────────────────────────┤
│ • BigQuery domains          │        │ • Custom domains only       │
│ • Production GCS            │        │ • fake-gcs-server           │
│ • ~2000 domains             │        │ • Configurable sample size  │
│ • Full processing           │        │ • Local metrics tracking    │
│                             │        │ • Requires Docker container │
│ Invocation:                 │        │                             │
│ --dst-gcp-project=...       │        │ Invocation:                 │
│ --dst-gcs-bucket=...        │        │ --local                     │
│                             │        │ --sample-size=20            │
└─────────────────────────────┘        └─────────────────────────────┘
```

## Data Flow

### Phase 1: Domain Collection

**Sources:**
- **BigQuery** (`io/domain_data_downloader.py`): Queries Tranco rankings for top domains
- **Custom Domains** (`enrichments/custom_domains.py`): Manually curated domain list
- **Custom Favicons** (`enrichments/custom_favicons.py`): Pre-defined favicon URLs for domains that block scrapers
- **Partner Favicons** (`enrichments/partner_favicons.py`): Partner-provided favicon URLs

**Process:**
1. `domain_data_downloader.py` queries BigQuery for ranked domains
2. Merges with `CUSTOM_DOMAINS` list
3. Returns list of domains with rank, categories, and TLD information

### Phase 2: Domain Processing

**Orchestrator:** `processing/domain_processor.py`

For each domain, the processor follows this workflow:

#### Step 2.1: Check Custom Favicon First (Priority)
- Looks up domain in `custom_favicons.py` mapping
- If found:
  - Downloads the custom favicon using `io/async_favicon_downloader.py`
  - Uploads to GCS via `io/domain_metadata_uploader.py`
  - Uses capitalized domain name as title
  - Returns immediately (skips scraping)

#### Step 2.2: Web Scraping (Fallback)
If no custom favicon exists, scrape the website:

**Tools:**
- `scrapers/web_scraper.py`: Opens URLs using MechanicalSoup
  - User agent: Firefox 114 on macOS
  - Timeout: 15 seconds
  - Follows redirects
  - Tries `https://domain.com`, then `https://www.domain.com` if first fails

**What is scraped:**
- HTML page content (BeautifulSoup parser)
- Page title from `<head><title>` tag

#### Step 2.3: Favicon Extraction

**Extractor:** `favicon/favicon_extractor.py`
**Scraper:** `scrapers/favicon_scraper.py`

Favicon sources are processed in priority order (up to 5 icons max):

1. **Link tags** (Highest priority)
   - `<link rel="icon">`
   - `<link rel="shortcut icon">`
   - `<link rel="apple-touch-icon">`
   - `<link rel="apple-touch-icon-precomposed">`
   - Other icon-related link tags

2. **Meta tags**
   - `<meta name="apple-touch-icon">`
   - `<meta name="msapplication-TileImage">`

3. **Default location**
   - `/favicon.ico` at domain root

4. **Web App Manifest** (Lowest priority, only if needed)
   - Parses `<link rel="manifest">` JSON
   - Extracts icons array

**Filtering:**
- Skips data URLs (`data:image/...`)
- Skips base64-encoded manifests
- Resolves relative URLs to absolute URLs

#### Step 2.4: Favicon Download & Processing

**Downloader:** `io/async_favicon_downloader.py`
**Processor:** `favicon/favicon_processor.py`

**Download strategy:**
- Concurrent downloads using asyncio
- Batch size: 5 favicons at a time
- Handles exceptions gracefully (returns None for failures)

**Processing phases:**

**Phase A: SVG Processing (Highest priority)**
- SVG favicons are preferred (scalable, high quality)
- Downloads all SVG candidates
- Skips masked SVGs (designed for specific UI contexts)
- First valid, non-masked SVG is uploaded immediately
- Returns without processing bitmaps

**Phase B: Bitmap Processing (Fallback)**
Only runs if no suitable SVG found:
- Downloads bitmap images in batches
- Extracts dimensions using PIL
- Compares candidates using selection rules

#### Step 2.5: Favicon Selection Rules

**Selector:** `favicon/favicon_selector.py`

Selection criteria (in order):

1. **Source Priority** (lower number = higher priority)
   - Link tags: Priority 1
   - Meta tags: Priority 2
   - Manifest: Priority 3
   - Default: Priority 4

2. **Dimensions** (for same source type)
   - Uses minimum of width/height (handles non-square images)
   - Larger dimensions preferred
   - Must meet minimum width requirement (configurable, default 48px)

**Example:**
- A 64×64 favicon from a link tag beats a 128×128 from manifest
- A 64×64 from link tag beats a 48×48 from same link tag
- A 32×32 favicon is rejected (below minimum width)

#### Step 2.6: Upload & Storage

**Uploader:** `io/domain_metadata_uploader.py`

- Computes SHA-256 hash of favicon content
- Generates filename: `favicons/{hash}_{size}.{ext}`
- Uploads to GCS bucket
- Returns public CDN URL
- Checks if file exists (skips upload if `force_upload=false`)

#### Step 2.7: Title Validation

**Validator:** `validators.py`

Extracted titles are validated against known error patterns:

**Rejected patterns:**
- "Attention Required", "Access denied"
- "Just a moment...", "Loading…"
- "404", "502 Bad Gateway", "503 Service..."
- "Captcha Challenge", "Robot or human"
- "Your request has been blocked"
- And 20+ other error/bot-detection messages

**Fallback:** If title is invalid or missing, uses capitalized domain name

### Phase 3: Manifest Construction

**Builder:** `processing/manifest_builder.py`

#### Top Picks Manifest
Combines domain data with extracted metadata:
```json
{
  "domains": [
    {
      "rank": 1,
      "domain": "example",
      "url": "https://example.com",
      "title": "Example Domain",
      "icon": "https://cdn.example.com/favicons/abc123_1024.png",
      "categories": [1, 2],
      "serp_categories": [1],
      "source": "top-picks"
    }
  ]
}
```

**Filtering rules:**
- Domains without valid URLs are excluded
- Custom domains without favicons are excluded
- Top-picks domains are always included (even without favicons)

#### Partner Manifest
Processes partner favicon URLs:
- Downloads each partner favicon
- Uploads to GCS
- Records original URL and GCS URL mapping

#### Errors Manifest
Tracks domains where favicon extraction failed:
```json
{
  "errors": [
    {
      "domain": "example.com",
      "error_reason": "web_scraping_failed"
    },
    {
      "domain": "another-site.com",
      "error_reason": "below_minimum_width"
    }
  ]
}
```

**Common error reasons:**

*Blocklist & Access:*
- `domain_in_blocklist`: Domain is in our internal blocklist (TOP_PICKS_BLOCKLIST)
- `blocked_by_bot_protection: HTTP {code}`: Website blocked the scraper (Cloudflare, captcha, etc.)
- `http_403_forbidden`: Access denied by server
- `http_503_service_unavailable`: Server temporarily unavailable
- `http_{code}_server_error`: Server returned 5xx error
- `http_{code}_client_error`: Client error (4xx)

*Connection & Scraping:*
- `connection_failed`: Timeout or network error
- `domain_mismatch_after_redirect`: Redirected to different domain
- `scraping_exception_{type}`: Exception during scraping (with exception type)

*Favicon Extraction:*
- `no_favicons_found`: Website opened but no favicon tags found
- `no_valid_favicon_urls`: Favicon tags found but URLs are invalid
- `all_favicons_invalid_format`: All favicon images failed PIL validation (cannot decode)
- `no_suitable_favicon_found: {n}/{total} images failed validation`: Some images failed validation, none suitable
- `no_suitable_favicon_found`: Favicons downloaded but none met requirements
- `below_minimum_width`: All favicons below minimum width requirement
- `favicon_extraction_exception`: Exception during favicon extraction
- `processing_exception`: General processing error

**Storage:**
- Timestamped file: `{timestamp}_errors.json`
- Latest file: `errors_latest.json`
- Uploaded to same GCS bucket as top_picks.json
- Local mode saves to `./local_data/errors_latest.json`

### Phase 4: Diff & Upload

**Diff:** `io/domain_metadata_diff.py`
- Downloads previous `top_picks_latest.json` from GCS
- Compares domains: unchanged, added domains, added URLs
- Generates diff report

**Upload:** `io/domain_metadata_uploader.py`
- Uploads timestamped file: `{timestamp}_top_picks.json`
- Overwrites `top_picks_latest.json`
- Both files stored in GCS bucket

## Execution Modes

### Normal Mode (Production)

**Purpose:** Process domains from BigQuery for production use

**Infrastructure:**
- Connects to Google Cloud BigQuery
- Uploads to production GCS bucket
- Processes ~2000 domains

**Invocation:**
```bash
merino-jobs navigational-suggestions prepare-domain-metadata \
  --src-gcp-project=<project> \
  --dst-gcp-project=<project> \
  --dst-gcs-bucket=<bucket> \
  --dst-cdn-hostname=<cdn>
```

**Implementation:** `modes/normal_mode.py`

### Local Mode (Development)

**Purpose:** Test changes locally without BigQuery or production GCS

**Infrastructure:**
- Uses `CUSTOM_DOMAINS` instead of BigQuery
- Connects to fake-gcs-server (Docker container)
- Processes configurable sample size (default: 20 domains)
- Saves metrics locally

**Requirements:**
1. Docker must be running
2. GCS emulator will be started automatically (or start manually with `make docker-compose-up`)

**Invocation (Recommended - uses Makefile):**
```bash
# Run with defaults (20 domains)
make nav-suggestions

# Run with custom sample size
make nav-suggestions SAMPLE_SIZE=50

# Run with monitoring enabled
make nav-suggestions SAMPLE_SIZE=50 ENABLE_MONITORING=true

# Run with custom output directory
make nav-suggestions METRICS_DIR=./my_data
```

The Makefile target handles:
- Starting the fake-gcs-server Docker container
- Running the job
- Stopping the container when finished

**Manual Invocation:**
```bash
# 1. Start the GCS emulator
docker compose -f dev/docker-compose.yaml up -d fake-gcs

# 2. Run the job
merino-jobs navigational-suggestions prepare-domain-metadata \
  --local \
  --sample-size=50 \
  --metrics-dir=./local_data

# 3. Stop the emulator when done
docker compose -f dev/docker-compose.yaml down fake-gcs
```

**Implementation:** `modes/local_mode_runner.py`

**Helpers:** `modes/local_mode_helpers.py`
- `LocalDomainDataProvider`: Provides sample domains
- `LocalMetricsCollector`: Tracks processing metrics

**Output:**
- `./local_data/top_picks_latest.json`: Generated manifest
- `./local_data/errors_latest.json`: Domains that failed favicon extraction
- `./local_data/metrics.json`: Processing statistics
- `./local_data/custom_favicon_usage.json`: Custom favicon hit rate

## Configuration

**Environment variables:**
- `STORAGE_EMULATOR_HOST`: GCS emulator endpoint (local mode only)

**CLI Options:**
- `--src-gcp-project`: BigQuery source project
- `--dst-gcp-project`: GCS destination project
- `--dst-gcs-bucket`: GCS bucket name
- `--dst-cdn-hostname`: CDN hostname for favicon URLs
- `--force-upload`: Re-upload existing favicons
- `--min-favicon-width`: Minimum favicon width (default: 48)
- `--write-xcom`: Write Airflow XCom file
- `--monitor`: Enable system resource monitoring
- `--local`: Enable local mode
- `--sample-size`: Domains to process in local mode (default: 20)
- `--metrics-dir`: Local metrics output directory (default: `./local_data`)

**Makefile Variables (for `make nav-suggestions`):**
- `SAMPLE_SIZE`: Number of domains to process (default: 20)
- `METRICS_DIR`: Output directory (default: `./local_data`)
- `ENABLE_MONITORING`: Enable monitoring (default: false)
- `NAV_OPTS`: Additional CLI options to pass through

## Key Constants

**HTTP Configuration** (`constants.py`):
- User-Agent: Firefox 114.0
- Timeout: 15 seconds
- Request headers: Mimics Firefox browser

**Processing Limits:**
- Max favicons per domain: 5
- Chunk size: 25 domains (memory management)
- Favicon batch size: 5 (concurrent downloads)

**Source Priority:**
```python
{
    "link": 1,      # Highest
    "meta": 2,
    "manifest": 3,
    "default": 4    # Lowest
}
```

## Metrics & Monitoring

**System Monitoring** (`--monitor` flag):
- CPU usage per chunk
- Memory usage per chunk
- Processing time per chunk

**Local Mode Metrics:**
- Domains processed
- Favicons found
- Custom favicon usage rate
- Processing success rate
- Average processing time

## Error Handling

**Domain-level failures:**
- Return empty metadata (`url=None, title=None, icon=None`)
- Log error details
- Continue processing remaining domains

**Chunk-level isolation:**
- Each chunk processed independently
- Downloader reset between chunks (prevents connection leaks)
- Exceptions in one domain don't affect others

**Graceful degradation:**
- Failed favicon downloads return None
- Invalid titles fall back to domain name
- Missing GCS diff file creates empty baseline
