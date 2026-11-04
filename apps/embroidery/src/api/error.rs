//! The error type every handler returns.

use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use serde_json::json;

pub type AppResult<T> = Result<T, AppError>;

/// Maps each failure to a status and a JSON body:
/// `{"error": {"type": "internal_error", "message": "..."}}`.
///
/// Variants are added as handlers need them.
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    /// Logged with its full chain; the client gets a generic message, so that internal details
    /// such as file paths never leak into responses.
    #[error(transparent)]
    Internal(#[from] anyhow::Error),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_type, message) = match &self {
            Self::Internal(err) => {
                tracing::error!(error = ?err, "internal server error");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "internal_error",
                    "an internal error occurred",
                )
            }
        };
        let body = json!({ "error": { "type": error_type, "message": message } });
        (status, Json(body)).into_response()
    }
}
