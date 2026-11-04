//! Logging setup: MozLog JSON for deployments, human-readable lines for local work.
//!
//! Depends on `config` only. OpenTelemetry, Sentry and metrics join this module later.

mod mozlog;

use tracing_subscriber::{EnvFilter, fmt, layer::SubscriberExt, util::SubscriberInitExt};

use crate::config::{LogFormat, LoggingConfig};

/// Installs the global `tracing` subscriber. Call once, before the first event.
///
/// # Panics
///
/// Panics if a global subscriber is already installed, which is a programming error in `main`.
pub fn init(config: &LoggingConfig) {
    // `Config::load` has validated the directive, so `new` won't drop any part of it.
    let registry = tracing_subscriber::registry().with(EnvFilter::new(&config.level));
    match config.format {
        LogFormat::Mozlog => registry.with(mozlog::layer(std::io::stdout)).init(),
        LogFormat::Pretty => registry.with(fmt::layer()).init(),
    }
}
