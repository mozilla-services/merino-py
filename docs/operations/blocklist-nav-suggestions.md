# Navigational Suggestions Job Blocklist
The Navigational Suggestions Job blocklist is contained in `merino/jobs/navigational_suggestions/data/domain_blocklist.json`.
This static file is read and used when running the indexing job and prevents the included domains from being added.

## Add to Blocklist
The Jobs CLI commands manages the blocklist. Modifying the raw JSON file is possible, but not recommended.

From the `merino-py` directory root, run `merino-jobs navigational-suggestions blocklist <add|remove|apply> <domain_name>`.

Use `add` and `remove` to modify domains in the blocklist.
Use `apply` to apply the blocklist locally.
You can override the blocklist path using `--blocklist-path <path>`.
You can also override the top picks file path using `--top-picks-path <path>`.

The domains added to the blocklist will only be blocked if you run the Navigational Suggestions Domain List Job again. You then have to check the new blocklist and `top_picks.json` file generated from the job into source control.

Once you've added and committed the new blocklist and `top_picks.json` file, merge in the branch with changes and deploy Merino.

The `merino/jobs/navigational_suggestions/__init__.py` file contains all logic for managing the blocklist.

For CLI directions, run `merino-jobs navigational-suggestions blocklist --help`.
