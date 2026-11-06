//! State shared by every handler.

/// Cheap to clone: handlers receive a copy per request.
///
/// Empty until the service has a backend; the database pool and the GCS client go here.
#[derive(Clone, Default)]
pub struct AppState {}
