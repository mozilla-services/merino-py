# Navigational Suggestions Job Blocklist
The Navigational Suggestions Job blocklist is contained in `merino/jobs/navigational_suggestions/data/domain_blocklist.json`.
This static file is read and used when running the indexing job and prevents the included domains from being added.

## Add to Blocklist
The Jobs CLI commands manages the blocklist. Modifying the raw JSON file is possible, but not recommended.

All commands should be run from the `merino-py` root directory.
Steps 1 - 4 are run locally.

1. Add domain (second-level domain): `merino-jobs navigational-suggestions blocklist add <domain_name>`.
2. Apply changes: `merino-jobs navigational-suggestions blocklist apply`. This removes blocked domain from `top_picks.json` if present.
3. Ensure that [`domain_blocklist.json`](/merino/jobs/navigational_suggestions/data/domain_blocklist.json) has the new added blocked domain and that the [`top_picks.json`](/dev/top_picks.json) file does not contain that domain.
4. Add the `domain_blocklist.json` and `top_picks.json` to source control, open a PR and merge in the changes.

If you wish to create a new `top_picks.json` file with the most recent top domains and apply the updated blocklist, these steps describe how to run the Airflow job once the blocklist is updated and merged in:

5. After image has been built, re-run the Airflow job [here](https://workflow.telemetry.mozilla.org/dags/merino_jobs/graph).
6. Add the newly generated `top_picks.json` file to source control, open a PR, merge the branch, and deploy Merino. 

Until Merino is deployed with the new `top_picks.json` file, the domain block will remain inactive.

Notes: You can override the blocklist path using `--blocklist-path <path>`.
You can also override the top picks file path using `--top-picks-path <path>`.

## Remove from Blocklist
Instructions are all the same as [Add to Blocklist](#Add_to_Blocklist), except replace step 1 with:
1.  Remove domain: `merino-jobs navigational-suggestions blocklist remove <domain_name>`.

The [`merino/jobs/navigational_suggestions/__init__.py`](/merino/jobs/navigational_suggestions/__init__.py) file contains all logic for managing the blocklist.

For CLI man page, run: `merino-jobs navigational-suggestions blocklist --help`.
