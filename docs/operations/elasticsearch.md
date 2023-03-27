# Elasticsearch Operations

We use Elasticsearch as a source of data for one of our providers.
This page documents some of the commands that we want to run on the cluster.

## Elasticsearch Index Policy

We want to ensure that the index expire after 30 days,
so we need to add a lifecycle policy for this deletion to happen.

The command to run in Kibana to add this policy:

```
PUT _ilm/policy/enwiki_policy
{
  "policy": {
    "phases": {
      "delete": {
        "min_age": "30d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

## Closed Index Recovery

The indexing job currently [closes the index](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-close.html)
after it migrates the alias to point to the new index.
Closing the index removes the ability to query from the index
but also reduces the heap memory usage when the index is not actively being queried.

If there is a situation where we need to recover a closed index to be the main index,
we will need to do the following:

1. [Re-open the index](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-open-close.html)
2. Point the [index alias](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-aliases.html) to the recovered index
