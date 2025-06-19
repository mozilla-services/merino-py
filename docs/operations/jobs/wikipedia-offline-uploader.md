# Merino Jobs Operation

## Wikipedia Offline Uploader Job

The wikipedia offline uploader is a job that uploads wikipedia suggestions data to remote settings.

The job consist of a single command called `upload`

The job retrieves wiki data for the last N days (default to 90) from `https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{language}.wikipedia.org/{access_type}`
and the data is filtered using our wikipedia blocklists and then is structured into suggestion data.

### Usage
```
uv run merino-jobs wiki-offline-uploader upload \
    --server https://remote-settings-dev.allizom.org \
    --collection quicksuggest-other \
    --languages en,fr,it \
    --auth "Bearer ..."
```

