//! Domain types: entity URIs, kinds, roles, variants, formats and fetch outcomes.
//!
//! Depends on the standard library, `serde` and `thiserror` only. No axum, sqlx, reqwest or
//! `google_cloud_*`, so that every other layer can use these types and tests need no I/O.
