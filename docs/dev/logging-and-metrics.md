# Logging and Metrics

To get data out of Merino and into observable systems, we use _metrics_ and
_logging_. Each has a unique use case. Note that in general, because of the scale
we work at, adding a metric or log event in production is not free, and if we
are careless can end up costing quite a bit. Record what is needed, but don't go
over board.

All data collection that happens in production (logging at INFO, WARN, or ERROR
levels; and metrics) should be documented in [`docs/data.md`](../data.md).

## Logging

Merino uses [MozLog][] for structured logging. Logs can be recorded through the
standard Python `logging` module. Merino can output logs in various formats,
including a JSON format (MozLog) for production. A pretty, human readable format
is also provided for development and other use cases.

[mozlog]: https://firefox-source-docs.mozilla.org/mozbase/mozlog.html

### Types

MozLog requires that all messages have a `type` value. By convention, we use
the name of the Python module, where the log record get issued, to populate this
field. For example:

```py
import logging

logger = logging.getLogger(__name__)

# The `type` field of the log record will be the same as `__name__`.
logger.info("A new log message", data=extra_fields)
```

In general, the log _message_ ("An empty MultiProvider was created") and the log
_type_ should both tell the reader what has happened. The difference is that the
message is for humans and the type is for machines.

### Levels

Tracing provides five log levels that should be familiar. This is what we mean
by them in Merino:

- `CRITICAL` - There was a serious error indicating that the program itself may
  be unable to continue running.

- `ERROR` - There was a problem, and the task was not completable. This usually
  results in a 500 being sent to the user. All error logs encountered in
  production are reported to Sentry and should be considered a bug. If it isn't
  a bug, it shouldn't be logged as an error.

- `WARNING` - There was a problem, but the task was able to recover. This
  doesn't usually affect what the user sees. Warnings are suitable for
  unexpected but "in-spec" issues, like a sync job not returning an empty set or
  using a deprecated function. These are not reported to Sentry.

- `INFO` - This is the default level of the production service. Use for logging
  that something happened that isn't a problem and we care about in production.
  This is the level that Merino uses for it's one-per-request logs and sync
  status messages. Be careful adding new per-request logs at this level, as they
  can be expensive.

- `DEBUG` - This is the default level for developers running code locally. Use
  this to give insight into how the system is working, but keep in mind that
  this will be on by default, so don't be too noisy. Generally this should
  summarize what's happening, but not give the small details like a log line for
  every iteration of a loop. Since this is off in production, there are no cost
  concerns.

## Metrics

Merino metrics are reported as [Statsd][] metrics.

[statsd]: https://www.datadoghq.com/blog/statsd/.

Unlike logging, the primary way that metrics reporting can cost a lot is in
_cardinality_. The number of metric IDs we have and the combination of tag
values that we supply. Often the number of individual events doesn't matter as
much, since multiple events are aggregated together.
