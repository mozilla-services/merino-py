# Navigational Suggestions Job Blocklist
The Navigational Suggestions Job blocklist is contained in `merino/jobs/navigational_suggestions/data/domain_blocklist.json`.
This static file is read and used when running the indexing job and prevents the included domains from being added.

## Add to Blocklist
You can modify the raw json file but it is preferable to use the jobs CLI commands to manage the blocklist.
The `merino/jobs/navidational_suggestions/__init__.py` file contains all logic for managing the blocklist.

For CLI directions, run `merino-jobs navigational-suggestions blocklist --help`.

From the `merino-py` directory root, run `merino-jobs navigational-suggestions blocklist <add|remove|apply> <domain_name>`.
Use `add` and `remove` to modify domains in the blocklist.
Use `apply` to apply the blocklist locally.
You can override the blocklist path using `--blocklist-path <path>`.
You can also override the top picks file path using `--top-picks-path <path>`.