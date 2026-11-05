//! HTTP API: routes, middleware, shared state, `AppError` and the Dockerflow handlers.
//!
//! May depend on `catalog`, `domain` and `config`. Handlers stay thin: extract, call `catalog`,
//! respond. No SQL here.

mod dockerflow;
mod error;
mod state;

use std::{any::Any, future::Future, time::Duration};

use axum::{
    Router,
    http::{Request, Response, StatusCode},
    response::IntoResponse as _,
    routing::get,
};
use tokio::net::TcpListener;
use tower::ServiceBuilder;
use tower_http::{
    catch_panic::CatchPanicLayer,
    request_id::{MakeRequestUuid, PropagateRequestIdLayer, RequestId, SetRequestIdLayer},
    timeout::TimeoutLayer,
    trace::TraceLayer,
};
use tracing::Span;

pub use error::{AppError, AppResult};
pub use state::AppState;

/// Builds the router with every route and the middleware stack.
///
/// Requests that take longer than `request_timeout` get a 503.
pub fn router(state: AppState, request_timeout: Duration) -> Router {
    // Outermost first: the request ID exists before the trace span opens, so the span and every
    // event inside it include it; panics and timeouts become responses inside the span.
    let middleware = ServiceBuilder::new()
        .layer(SetRequestIdLayer::x_request_id(MakeRequestUuid))
        .layer(PropagateRequestIdLayer::x_request_id())
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(make_span)
                .on_response(on_response),
        )
        .layer(CatchPanicLayer::custom(panic_response))
        // 503, not 408: 408 tells the client that it was too slow to send the request.
        .layer(TimeoutLayer::with_status_code(
            StatusCode::SERVICE_UNAVAILABLE,
            request_timeout,
        ));

    Router::new()
        .route("/__lbheartbeat__", get(dockerflow::lbheartbeat))
        .route("/__heartbeat__", get(dockerflow::heartbeat))
        .route("/__version__", get(dockerflow::version))
        .with_state(state)
        .layer(middleware)
}

/// Serves `app` on `listener` until `shutdown` resolves, then lets in-flight requests finish.
///
/// # Errors
///
/// Fails if accepting connections fails.
pub(crate) async fn serve(
    listener: TcpListener,
    app: Router,
    shutdown: impl Future<Output = ()> + Send + 'static,
) -> std::io::Result<()> {
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown)
        .await
}

/// Resolves on SIGTERM, which Kubernetes sends before killing the pod, or on Ctrl+C.
pub(crate) async fn shutdown_signal() {
    let ctrl_c = async {
        if let Err(err) = tokio::signal::ctrl_c().await {
            tracing::error!(error = %err, "failed to listen for Ctrl+C");
            std::future::pending::<()>().await;
        }
    };
    #[cfg(unix)]
    let terminate = async {
        use tokio::signal::unix::{SignalKind, signal};
        match signal(SignalKind::terminate()) {
            Ok(mut sigterm) => {
                sigterm.recv().await;
            }
            Err(err) => {
                tracing::error!(error = %err, "failed to listen for SIGTERM");
                std::future::pending::<()>().await;
            }
        }
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        () = ctrl_c => {}
        () = terminate => {}
    }
    tracing::info!("shutdown signal received, finishing in-flight requests");
}

fn make_span<B>(request: &Request<B>) -> Span {
    let request_id = request
        .extensions()
        .get::<RequestId>()
        .and_then(|id| id.header_value().to_str().ok())
        .unwrap_or_default();
    tracing::info_span!(
        "request",
        method = %request.method(),
        path = request.uri().path(),
        request_id,
    )
}

fn on_response<B>(response: &Response<B>, latency: Duration, _span: &Span) {
    tracing::info!(
        status = response.status().as_u16(),
        latency_ms = u64::try_from(latency.as_millis()).unwrap_or(u64::MAX),
        "request finished"
    );
}

#[expect(
    clippy::needless_pass_by_value,
    reason = "`CatchPanicLayer` passes the payload by value"
)]
fn panic_response(panic: Box<dyn Any + Send + 'static>) -> Response<axum::body::Body> {
    let message = panic
        .downcast_ref::<&str>()
        .copied()
        .or_else(|| panic.downcast_ref::<String>().map(String::as_str))
        .unwrap_or("non-string panic payload");
    AppError::Internal(anyhow::anyhow!("handler panicked: {message}")).into_response()
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use axum::{Router, routing::get};
    use tokio::{net::TcpListener, sync::oneshot};

    use super::serve;

    #[tokio::test]
    async fn graceful_shutdown_finishes_in_flight_request() {
        let app = Router::new().route(
            "/slow",
            get(|| async {
                tokio::time::sleep(Duration::from_millis(300)).await;
                "done"
            }),
        );
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
        let server = tokio::spawn(serve(listener, app, async {
            shutdown_rx.await.ok();
        }));

        // A raw HTTP/1.1 request keeps the test free of an HTTP client dependency.
        let request = tokio::spawn(async move {
            use tokio::io::{AsyncReadExt, AsyncWriteExt};
            let mut stream = tokio::net::TcpStream::connect(addr).await.unwrap();
            stream
                .write_all(b"GET /slow HTTP/1.1\r\nhost: test\r\nconnection: close\r\n\r\n")
                .await
                .unwrap();
            let mut response = String::new();
            stream.read_to_string(&mut response).await.unwrap();
            response
        });

        tokio::time::sleep(Duration::from_millis(100)).await;
        shutdown_tx.send(()).unwrap();

        let response = request.await.unwrap();
        assert!(response.starts_with("HTTP/1.1 200"), "{response}");
        assert!(response.ends_with("done"), "{response}");
        server.await.unwrap().unwrap();
    }
}
