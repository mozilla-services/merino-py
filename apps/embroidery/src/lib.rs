//! Embroidery, Mozilla's image service: entities, images and fetching for Firefox favicons and
//! logos.
//!
//! Dependency rule: `api` and `jobs` call `catalog`, which uses `infra`. All of them may use
//! `domain`, and `domain` uses no framework crate (axum, sqlx, reqwest, `google_cloud_*`).

pub mod api;
pub mod catalog;
pub mod cli;
pub mod config;
pub mod domain;
pub mod infra;
pub mod jobs;
pub mod scraper;
pub mod telemetry;

use std::net::SocketAddr;

use anyhow::Context as _;
use tokio::net::TcpListener;

pub use api::router;

use crate::{api::AppState, config::Config};

/// Binds the configured address and serves the HTTP API until SIGTERM or Ctrl+C, then lets
/// in-flight requests finish.
///
/// # Errors
///
/// Fails if the address can't be bound or accepting connections fails.
pub async fn run_server(config: Config) -> anyhow::Result<()> {
    let addr = SocketAddr::new(config.server.host, config.server.port);
    let listener = TcpListener::bind(addr)
        .await
        .with_context(|| format!("failed to bind {addr}"))?;
    let app = router(AppState::default(), config.server.request_timeout);

    tracing::info!(addr = %listener.local_addr()?, env = %config.env, "listening");
    api::serve(listener, app, api::shutdown_signal())
        .await
        .context("HTTP server failed")
}
