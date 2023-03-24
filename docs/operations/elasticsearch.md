# Elasticsearch Operations

We use Elasticsearch as a source of data for one of our providers.
This page documents some of the commands that we want to run on the cluster.

### Elasticsearch Index Policy

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