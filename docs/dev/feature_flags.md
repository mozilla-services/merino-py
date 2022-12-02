g# Feature Flags

## Usage

Do you plan to release code behind a feature flag? Great! 😃

Your feature flag needs to be defined first. If it's already defined, go ahead.
Otherwise check the configuration section [below](#configuration) before you
continue.

Use the following line in API endpoint code to gain access to the feature flags
object:

```python
feature_flags: FeatureFlags = request.scope[ScopeKey.FEATURE_FLAGS]
```

Then check whether a certain feature flag, such as `example`, is enabled by calling:

```python
if feature_flags.is_enabled("example"):
    print("feature flag 'example' is enabled! 🚀")
```

When you do that, the decision (whether the feature flag is enabled or not) is
recorded and stored in a `dict` on the `decisions` attribute of the feature
flags object.

## Implementation

The feature flags system in Merino consists of three components:

| Description | Location |
| ----------- | -------- |
| A FastAPI middleware that reads the query parameter `sid` sent by the client application and sets a session ID for the current request based on that. | `merino/middleware/featureflags.py`|
| A `FeatureFlags` class which you can use to check if a certain feature flag is enabled. | `merino/featureflags.py` |
| A local directory containing static files that define and configure feature flags for Merino. | `merino/configs/flags/` |

## Configuration

Currently two bucketing schemes are supported: `random` and `session`.

### Random

Random does what it says on the tin. It generates a random bucketing ID for
every flag check.

### Session

Session bucketing uses the session ID of the request as the bucketing key so
that feature checks within a given search session would be consistent.

### Fields

Each flag defines the following fields:

```toml
[default.flags.<flag_name>]
scheme = 'session'
enabled = 0.5
```

| Field | Description |
| ----------- | -------- |
| `scheme` | This is the bucketing scheme for the flag. Allowed values are `'random'` and `'session'` |
| `enabled` | This represents the % enabled for the flag and must be a float between `0` and `1` |


## Metrics

When submitting application metrics, feature flag decisions that were made while
processing the current request up to this point are **automatically** added as
tags to the emitted metrics.

The format of these tags is:

```
feature_flag.<feature_flag_name>
```

For more information about this see the `ClientMeta` meta class and the
`add_feature_flags` decorator in `merino/metrics.py`.

## Monitoring in Grafana

Because feature flag decisions are automatically added as tags to emitted
metrics, you can use them in your queries in Grafana. 📈

For example, if you want to group by decisions for a feature flag with name
`hello_world`, you can use `tag(feature_flag.hello_world)` in `GROUP BY` in
Grafana. You can also use `[[tag_feature_flag.hello_world]]` in the `ALIAS` for
panel legends.
