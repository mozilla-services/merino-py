# Reporting metrics in local development and tests

* Status: Proposed
* Deciders: raphael, lina
* Date: 2022-12-20

## Context and Problem Statement

merino-py emits counts, histograms, and timing metrics as it runs.
In production, these metrics are sent to Datadog, using an extension of the
[StatsD](https://github.com/statsd/statsd) protocol called [DogStatsD](https://docs.datadoghq.com/developers/dogstatsd).
For local development, merino-py provides the `metrics.dev_logger` config option,
which logs outgoing metrics to the console instead of sending them to Datadog.
merino-py also has integration tests that cover recording and emitting metrics.
How can we avoid relying on implementation details of  the `aiodogstatsd` client library
to suppress reporting to Datadog?

## Decision Drivers

1. Avoid future compatibility hazards when upgrading `aiodogstatsd`.
2. Make it easy for engineers to see what metrics are emitted while working on the code.
3. Maintain test coverage for merino-py's metrics.

## Considered Options

* A. Do nothing.
* B. Always send metrics to a live DogStatsD agent.
* C. Change merino-py's `metrics.Client` proxy to not call into `aiodogstatsd`.
* D. Subclass `aiodogstatsd.Client` to suppress sending metrics to DogStatsD.
* E. Extend merino-py's `metrics` module with pluggable backends for production and testing.
* F. Set up a mock DogStatsD endpoint that collects and checks metrics.
* G. Ask the `aiodogstatsd` authors to expose a reporting hook as part of their public API.

## Decision Outcome

TODO: Fill me in once we decide!

## Pros and Cons of the Options

### A. Do nothing.

This option would keep the code as it's written today:

1. When the `metrics.dev_logger` config option is set, `configure_metrics()` sets the pseudo-private
   `aiodogstatsd.Client._protocol` property to an instance of `metrics._LocalDatagramLogger`.
   `_LocalDatagramLogger` subclasses `aiodogstatsd.client.DatagramProtocol` to log metrics
   instead of sending them to DogStatsD.
   ([DISCO-2089](https://mozilla-hub.atlassian.net/browse/DISCO-2089))
2. merino-py's integration tests patch the pseudo-private `aiodogstatsd.Client._report()` method
   with a mock implementation.
   ([DISCO-2090](https://mozilla-hub.atlassian.net/browse/DISCO-2090))

#### Pros

* Currently working code!
* Doesn't require any engineering work now.
* `aiodogstatsd` is in maintenance mode, and unlikely to break merino-py's usage.

#### Cons

* Relying on non-public APIs could break merino-py if `aiodogstatsd` changes its implementation in the future.
* Assumes that merino-py will only ever report metrics to DogStatsD.

### B. Send metrics to a live DogStatsD agent.

This option would remove the `metrics.dev_logger` config option.
Instead, engineers would need to run a DogStatsD agent locally, and configure merino-py to use that agent.

#### Pros

* A single path for metrics reporting in local development, testing, and production.
* Less code in merino-py for metrics logging.
* Unofficial local DogStatsD agents exist,
  written in [Go](https://github.com/jonmorehouse/dogstatsd-local) and
  [Ruby](https://github.com/drish/dogstatsd-local).
* Local DogStatsD agents can log metrics in different formats.

#### Cons

* Engineers would need to configure and run a separate service when working locally.
* Requires an unofficial local DogStatsD agent.
  The [official DogStatsD agent](https://hub.docker.com/r/datadog/dogstatsd) is only offered as a Docker container
  that reports metrics to Datadog, and doesn't support custom or local-only backends.
  The plain StatsD agent, which
  [does support custom backends](https://github.com/statsd/statsd/blob/master/docs/backend.md),
  doesn't support the DogStatsD extensions (histograms) that merino-py uses.
* Only suitable for local development.
  Setting up a live DogStatsD agent would be more cumbersome to do in the integration tests.
* Assumes that merino-py will only ever report metrics to DogStatsD.

### C. Change merino-py's `metrics.Client` proxy to not call into `aiodogstatsd` in testing.

merino-py's `metrics.Client` class currently proxies calls to `aiodogstatsd.Client`.
The proxy keeps track of all metrics calls for testing, and adds custom tags for feature flags.
We can extend the proxy to only log metrics to the console if `metrics.dev_logger` is set,
without forwarding them to the underlying `aiodogstatsd.Client`.

#### Pros

* Needs minimal changes to support metrics logging for gauges, counters, histograms, and one-off timings.
* Proxying calls avoids relying on implementation details of `aiodogstatsd`.

#### Cons

* Doesn't work for `aiodogstatsd.Client.{timeit, timeit_task}()`,
  which return thunks that call `aiodogstatsd.Client.timing()`.
  Since the proxy can't intercept these calls, it would need to reimplement these methods.
* Assumes that merino-py will only ever report metrics to DogStatsD.

### D. Subclass `aiodogstatsd.Client` to suppress sending metrics to StatsD in tests.

This option would change `metrics.Client` to be a subclass of `aiodogstatsd.Client`,  instead of proxying calls to it.
The subclass would override the `{gauge, increment, decrement, histogram, distribution, timing}()` methods
to log metrics if `metrics.dev_logger` is set.

#### Pros

* Involves making the same changes as Option C to support methods that don't return anything.
* Works for `aiodogstatsd.Client.{timeit, timeit_task}()` out of the box, without needing to reimplement them.

#### Cons

* Subclassing `aiodogstatsd.Client` relies on implementation details
  (for example, that `timeit_task()` calls `timing()` when it's done) that could change
  in a future version of `aiodogstatsd`.
* Assumes that merino-py will only ever report metrics to DogStatsD.

### E. Extend merino-py's `metrics` module with pluggable backends for production and testing.

This option would turn `metrics.Client` into a generic metrics interface  that can send metrics to any supported
backend: DogStatsD, the console, or another metrics provider (Graphite, InfluxDB) in the future.

#### Pros

* Doesn't rely on implementation details of `aiodogstatsd`.
* Makes it easy to use an integration test backend to verify recorded metrics.
* Can support any number of backends, without requiring substantial changes to merino-py or the metrics interface.

#### Cons

* Incurs the most engineering work out of all our options.
* Introduces another layer of abstraction that might not be useful beyond tests or local development.
* The new interface would need to reimplement convenience methods like `timeit_task()` from `aiodogstatsd`.

### F. Set up a mock DogStatsD endpoint that collects and checks metrics in tests.

This option would have the integration tests set up a UDP socket that collects, parses, and checks
the recorded metrics, following
[the same approach](https://github.com/Gr1N/aiodogstatsd/blob/4c363d795df04d1cc4c137307b7f91592224ed32/tests/conftest.py#L11-L13)
as the `aiodogstatsd` tests.
merino-py's `metrics.Client` would be configured to send metrics to this endpoint in tests.

#### Pros

* Integration tests wouldn't need to patch `aiodogstatsd.Client._report()`.

#### Cons

* The mock socket would need to parse the DogStatsD ping, which could introduce additional bugs.
* Replaces integration test usage only.
  This option doesn't address the `metrics.dev_logger` use case, and setting up a mock socket for local development
  would be more cumbersome.
* Assumes that merino-py will only ever report metrics to DogStatsD.

### G. Ask the `aiodogstatsd` authors to expose a reporting hook as part of their public API.

This option would involve changing `aiodogstatsd` to expose a public API for intercepting metrics before they're sent.
This could involve exposing `_protocol` and `_report()`, or adding a new API surface.

#### Pros

* Doesn't require substantial engineering work from our team.
* Provides a supported way to log and check metrics without relying on implementation details.

#### Cons

* We'd need to wait for the authors to consider, approve, implement, and publish a new version with our proposal.
  This could take an unknown amount of time.
* `aiodogstatsd` is stable (the last commit was December 2021), and the authors could reject
  making such a substantial changes to the interface.
* Commits the `aiodogstatsd` authors to maintaining a new API, of which we would be the only consumer.
* Assumes that merino-py will only ever report metrics to DogStatsD.
