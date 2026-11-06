//! A `tracing` event formatter for MozLog, the JSON format Mozilla's log pipeline parses
//! (<https://wiki.mozilla.org/Firefox/Services/Logging>).
//!
//! No maintained crate formats `tracing` events as MozLog: autopush-rs and syncstorage-rs still
//! use slog. One event becomes one line:
//!
//! ```json
//! {"Timestamp":1793270400000000000,"Type":"embroidery::api","Logger":"embroidery",
//!  "Hostname":"embroidery-7d9f","EnvVersion":"2.0","Severity":6,"Pid":1,
//!  "Fields":{"msg":"request finished","status":200,"path":"/__heartbeat__","latency_ms":3}}
//! ```

use std::{
    error::Error,
    fmt::{self, Write as _},
    time::{SystemTime, UNIX_EPOCH},
};

use serde::Serialize;
use serde_json::{Map, Value};
use tracing::{Event, Level, Subscriber, field::Field};
use tracing_subscriber::{
    Layer,
    field::Visit,
    fmt::{
        FmtContext, FormatEvent, FormattedFields,
        format::{JsonFields, Writer},
        writer::MakeWriter,
    },
    registry::{LookupSpan, Scope},
};

const LOGGER: &str = env!("CARGO_PKG_NAME");
const ENV_VERSION: &str = "2.0";

/// A `fmt` layer that writes MozLog lines to `make_writer`.
pub(super) fn layer<S, W>(make_writer: W) -> impl Layer<S>
where
    S: Subscriber + for<'a> LookupSpan<'a>,
    W: for<'w> MakeWriter<'w> + Send + Sync + 'static,
{
    tracing_subscriber::fmt::layer()
        // Span fields are stored as JSON, which `MozLog` parses back into `Fields`.
        .fmt_fields(JsonFields::new())
        .event_format(MozLog::new())
        .with_writer(make_writer)
}

struct MozLog {
    hostname: String,
    pid: u32,
}

impl MozLog {
    fn new() -> Self {
        Self {
            // Kubernetes sets `HOSTNAME` to the pod name. The standard library has no portable
            // hostname call, and `forbid(unsafe_code)` rules out calling libc directly.
            hostname: std::env::var("HOSTNAME").unwrap_or_else(|_| "unknown".to_owned()),
            pid: std::process::id(),
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "PascalCase")]
struct Entry<'a> {
    timestamp: i64,
    #[serde(rename = "Type")]
    kind: &'a str,
    logger: &'a str,
    hostname: &'a str,
    env_version: &'a str,
    severity: u8,
    pid: u32,
    fields: Map<String, Value>,
}

// Bound to `JsonFields`, so that the span fields in the extensions are always JSON.
impl<S> FormatEvent<S, JsonFields> for MozLog
where
    S: Subscriber + for<'a> LookupSpan<'a>,
{
    fn format_event(
        &self,
        ctx: &FmtContext<'_, S, JsonFields>,
        mut writer: Writer<'_>,
        event: &Event<'_>,
    ) -> fmt::Result {
        let mut fields = Map::new();
        // Root to leaf, so that inner spans override outer ones and the event overrides all.
        for span in ctx.event_scope().into_iter().flat_map(Scope::from_root) {
            let extensions = span.extensions();
            let Some(formatted) = extensions.get::<FormattedFields<JsonFields>>() else {
                continue;
            };
            // A span without fields formats as an empty string, not `{}`.
            if let Ok(Value::Object(span_fields)) = serde_json::from_str(formatted) {
                fields.extend(span_fields);
            }
        }
        event.record(&mut FieldVisitor(&mut fields));

        let metadata = event.metadata();
        let entry = Entry {
            timestamp: unix_nanos(SystemTime::now()),
            kind: metadata.target(),
            logger: LOGGER,
            hostname: &self.hostname,
            env_version: ENV_VERSION,
            severity: severity(*metadata.level()),
            pid: self.pid,
            fields,
        };
        let line = serde_json::to_string(&entry).map_err(|_| fmt::Error)?;
        writer.write_str(&line)?;
        writer.write_char('\n')
    }
}

/// Maps `tracing` levels to syslog severities, which MozLog uses.
fn severity(level: Level) -> u8 {
    match level {
        Level::ERROR => 3,
        Level::WARN => 4,
        Level::INFO => 6,
        Level::DEBUG | Level::TRACE => 7,
    }
}

fn unix_nanos(time: SystemTime) -> i64 {
    time.duration_since(UNIX_EPOCH).map_or(0, |since| {
        i64::try_from(since.as_nanos()).unwrap_or(i64::MAX)
    })
}

struct FieldVisitor<'a>(&'a mut Map<String, Value>);

impl FieldVisitor<'_> {
    fn insert(&mut self, field: &Field, value: impl Into<Value>) {
        // MozLog consumers expect the message under `msg`.
        let name = match field.name() {
            "message" => "msg",
            name => name,
        };
        self.0.insert(name.to_owned(), value.into());
    }
}

impl Visit for FieldVisitor<'_> {
    fn record_f64(&mut self, field: &Field, value: f64) {
        self.insert(field, value);
    }

    fn record_i64(&mut self, field: &Field, value: i64) {
        self.insert(field, value);
    }

    fn record_u64(&mut self, field: &Field, value: u64) {
        self.insert(field, value);
    }

    fn record_bool(&mut self, field: &Field, value: bool) {
        self.insert(field, value);
    }

    fn record_str(&mut self, field: &Field, value: &str) {
        self.insert(field, value);
    }

    fn record_error(&mut self, field: &Field, value: &(dyn Error + 'static)) {
        let mut message = value.to_string();
        let mut source = value.source();
        while let Some(cause) = source {
            // Writing to a `String` can't fail.
            let _ = write!(message, ": {cause}");
            source = cause.source();
        }
        self.insert(field, message);
    }

    fn record_debug(&mut self, field: &Field, value: &dyn fmt::Debug) {
        self.insert(field, format!("{value:?}"));
    }
}

#[cfg(test)]
mod tests {
    use std::{
        io,
        sync::{Arc, Mutex},
    };

    use tracing_subscriber::layer::SubscriberExt;

    use super::*;

    #[derive(Clone, Default)]
    struct Buffer(Arc<Mutex<Vec<u8>>>);

    impl io::Write for Buffer {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(buf);
            Ok(buf.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    /// Runs `emit` under a MozLog subscriber and returns one parsed JSON value per line.
    fn capture(emit: impl FnOnce()) -> Vec<Value> {
        let buffer = Buffer::default();
        let writer = buffer.clone();
        let subscriber = tracing_subscriber::registry().with(layer(move || writer.clone()));
        tracing::subscriber::with_default(subscriber, emit);

        let output = buffer.0.lock().unwrap();
        std::str::from_utf8(&output)
            .unwrap()
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect()
    }

    #[test]
    fn formats_event_with_span_fields() {
        let lines = capture(|| {
            let span = tracing::info_span!("request", request_id = "abc", path = "/outer");
            let _guard = span.enter();
            tracing::info!(target: "embroidery.http", status = 200_u16, path = "/__heartbeat__", latency_ms = 3_u64, "request finished");
        });

        insta::assert_json_snapshot!(lines[0], {
            ".Timestamp" => "[timestamp]",
            ".Hostname" => "[hostname]",
            ".Pid" => "[pid]",
        });
    }

    #[test]
    fn maps_levels_to_syslog_severity() {
        let lines = capture(|| {
            tracing::error!("e");
            tracing::warn!("w");
            tracing::info!("i");
            tracing::debug!("d");
            tracing::trace!("t");
        });

        let severities: Vec<_> = lines
            .iter()
            .map(|line| line["Severity"].as_u64().unwrap())
            .collect();
        assert_eq!(severities, [3, 4, 6, 7, 7]);
    }

    #[test]
    fn records_error_source_chain() {
        let err = ErrorWithSource(io::Error::other("disk full"));
        let lines =
            capture(|| tracing::error!(error = &err as &(dyn Error + 'static), "write failed"));

        assert_eq!(lines[0]["Fields"]["error"], "wrapper: disk full");
    }

    #[derive(Debug)]
    struct ErrorWithSource(io::Error);

    impl fmt::Display for ErrorWithSource {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            f.write_str("wrapper")
        }
    }

    impl Error for ErrorWithSource {
        fn source(&self) -> Option<&(dyn Error + 'static)> {
            Some(&self.0)
        }
    }
}
