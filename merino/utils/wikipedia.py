"""Shared utilities for requesting content from Wikipedia and other Wikimedia sites."""

# Wikimedia asks callers to identify themselves with a unique user agent, otherwise our
# requests can be blocked as bot traffic.
# See https://www.mediawiki.org/wiki/Wikimedia_REST_API
WIKIMEDIA_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Merino/1.0; +https://github.com/mozilla-services/merino-py)"
}
