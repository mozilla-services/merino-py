# Navigational Suggestions Job Blocklist
The Navigational Suggestions Job blocklist is contained in `merino/utils/blocklists.py`.
The `TOP_PICKS_BLOCKLIST` variable is used when running the indexing job and prevents the included domains from being added.

## Add to Blocklist
1. Go to [`merino/utils/blocklists.py`][utils-blocklist].
2. Add the second-level-domain to the `TOP_PICKS_BLOCKLIST` set.
3. Open a PR and merge in the changes to block this domain from being indexed.

## Remove from Blocklist
Repeat as above, just remove the domain from the `TOP_PICKS_BLOCKLIST` set.

* Note: removing from the blocklist means that the domain was likely not created during the Airflow job,
so if you wish to see it re-added, supposing it is still in the top 1000 domains, you have to re-run the airflow job.
See the instructions for this in the [jobs/navigational_suggestions docs][nav-suggestions].

[utils-blocklist]: https://github.com/mozilla-services/merino-py/blob/main/merino/utils/blocklists.py
[nav-suggestions]: ./jobs/navigational_suggestions.md
