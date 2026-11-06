//! Dockerflow endpoints through the full router and middleware stack.

#![allow(
    clippy::unwrap_used,
    reason = "test helpers panic on unexpected failures"
)]

use std::time::Duration;

use axum::{
    Router,
    body::Body,
    http::{Request, StatusCode, header},
};
use embroidery::{api::AppState, router};
use http_body_util::BodyExt as _;
use serde_json::{Value, json};
use tower::ServiceExt as _;

fn app() -> Router {
    router(AppState::default(), Duration::from_secs(5))
}

async fn get(app: Router, uri: &str) -> axum::response::Response {
    let request = Request::get(uri).body(Body::empty()).unwrap();
    app.oneshot(request).await.unwrap()
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

#[tokio::test]
async fn lbheartbeat_responds_with_empty_200() {
    let response = get(app(), "/__lbheartbeat__").await;

    assert_eq!(response.status(), StatusCode::OK);
    let body = response.into_body().collect().await.unwrap().to_bytes();
    assert!(body.is_empty());
}

#[tokio::test]
async fn heartbeat_responds_with_ok_status() {
    let response = get(app(), "/__heartbeat__").await;

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        body_json(response).await,
        json!({ "status": "ok", "checks": {} })
    );
}

#[tokio::test]
async fn version_responds_with_embedded_version_file() {
    let response = get(app(), "/__version__").await;

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()[header::CONTENT_TYPE], "application/json");
    let expected: Value = serde_json::from_str(include_str!("../../../version.json")).unwrap();
    assert_eq!(body_json(response).await, expected);
}

#[tokio::test]
async fn generates_and_returns_request_id() {
    let response = get(app(), "/__lbheartbeat__").await;

    let request_id = response.headers()["x-request-id"].to_str().unwrap();
    assert_eq!(request_id.len(), 36, "expected a UUID, got {request_id}");
}

#[tokio::test]
async fn propagates_incoming_request_id() {
    let request = Request::get("/__lbheartbeat__")
        .header("x-request-id", "from-the-load-balancer")
        .body(Body::empty())
        .unwrap();
    let response = app().oneshot(request).await.unwrap();

    assert_eq!(response.headers()["x-request-id"], "from-the-load-balancer");
}
