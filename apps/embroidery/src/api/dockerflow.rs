//! Dockerflow endpoints (<https://github.com/mozilla-services/Dockerflow>).

use axum::{Json, http::header, response::IntoResponse};
use serde::Serialize;

/// `GET /__lbheartbeat__`: liveness. Checks no backend, so that a slow dependency can't make
/// Kubernetes restart healthy pods.
pub(super) async fn lbheartbeat() {}

#[derive(Serialize)]
pub(super) struct Heartbeat {
    status: Status,
    checks: Checks,
}

/// One field per backend, named as Dockerflow reports it. Empty until the service has a backend.
#[derive(Serialize)]
struct Checks {}

#[derive(Serialize)]
#[serde(rename_all = "lowercase")]
enum Status {
    Ok,
}

/// `GET /__heartbeat__`: readiness.
pub(super) async fn heartbeat() -> Json<Heartbeat> {
    Json(Heartbeat {
        status: Status::Ok,
        checks: Checks {},
    })
}

/// The repository's `version.json`, embedded at compile time. CI overwrites the committed
/// placeholder with the build's commit and run URL before it builds the image, so the binary
/// reports the build it came from, and a missing file fails compilation instead of a request.
const VERSION_JSON: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/../../version.json"));

/// `GET /__version__`: the `version.json` embedded at build time.
pub(super) async fn version() -> impl IntoResponse {
    ([(header::CONTENT_TYPE, "application/json")], VERSION_JSON)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Runs against the file CI generates, so a malformed `version.json` fails the build
    /// instead of reaching `/__version__`.
    #[test]
    fn embedded_version_is_json_object() {
        let value: serde_json::Value = serde_json::from_str(VERSION_JSON).unwrap();

        for key in ["source", "version", "commit", "build"] {
            assert!(
                value[key].is_string(),
                "{key} missing or not a string in {value}"
            );
        }
    }
}
