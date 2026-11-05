//! Catalog writes shared by the API and the jobs: record an image, register an entity, apply an
//! override, block an entity.
//!
//! May depend on `domain` and `infra`. Owns transaction boundaries; callers never touch `infra`.
