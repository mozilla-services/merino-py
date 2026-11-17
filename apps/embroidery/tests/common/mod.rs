//! Helpers shared by the integration tests. Each helper starts its own container with
//! testcontainers and removes it when dropped, so tests share no state and need only Docker.

#![allow(
    clippy::expect_used,
    reason = "test helpers panic on unexpected failures"
)]

use std::time::Duration;

use reqwest::{Client, Url};
use serde_json::json;
use sqlx::PgPool;
use testcontainers::{
    ContainerAsync, GenericImage, Healthcheck, ImageExt,
    core::{IntoContainerPort, WaitFor, wait::HttpWaitStrategy},
    runners::AsyncRunner,
};

/// Same major version as Cloud SQL (`POSTGRES_18`).
const POSTGRES_TAG: &str = "18-alpine";
const POSTGRES_PORT: u16 = 5432;
const POSTGRES_PASSWORD: &str = "embroidery";

/// Same version as `dev/docker-compose.yaml`.
const FAKE_GCS_TAG: &str = "1.55.1";
const FAKE_GCS_PORT: u16 = 4443;

/// The container holds a single test's objects, so a fixed name can't collide.
const BUCKET: &str = "test";

/// An empty PostgreSQL server that only one test uses.
pub(crate) struct TestDb {
    // Declared before the container, so connections close before the server stops.
    pool: PgPool,
    _container: ContainerAsync<GenericImage>,
}

impl TestDb {
    /// Starts PostgreSQL and connects to it once it accepts TCP connections.
    pub(crate) async fn start() -> Self {
        let container = GenericImage::new("postgres", POSTGRES_TAG)
            .with_exposed_port(POSTGRES_PORT.tcp())
            // The image's entrypoint first runs a temporary server for initialization, which logs
            // the same "ready" line as the final one but listens only on the Unix socket. A TCP
            // `pg_isready` passes only once the final server is up.
            .with_wait_for(WaitFor::healthcheck())
            .with_health_check(
                Healthcheck::cmd_shell("pg_isready -h 127.0.0.1 -U postgres")
                    .with_interval(Duration::from_millis(250))
                    .with_retries(120),
            )
            .with_env_var("POSTGRES_PASSWORD", POSTGRES_PASSWORD)
            .start()
            .await
            .unwrap_or_else(|err| panic!("failed to start PostgreSQL; is Docker running? {err}"));

        let host = container.get_host().await.expect("container host");
        let port = container
            .get_host_port_ipv4(POSTGRES_PORT.tcp())
            .await
            .expect("PostgreSQL port is mapped");
        let url = format!("postgres://postgres:{POSTGRES_PASSWORD}@{host}:{port}/postgres");
        let pool = PgPool::connect(&url)
            .await
            .unwrap_or_else(|err| panic!("failed to connect to {url}: {err}"));

        Self {
            pool,
            _container: container,
        }
    }

    pub(crate) fn pool(&self) -> &PgPool {
        &self.pool
    }
}

/// A bucket on a fake-gcs-server that only one test uses.
pub(crate) struct TestBucket {
    http: Client,
    endpoint: Url,
    _container: ContainerAsync<GenericImage>,
}

impl TestBucket {
    /// Starts fake-gcs-server, waits until its JSON API responds, and creates the bucket.
    pub(crate) async fn create() -> Self {
        let container = GenericImage::new("fsouza/fake-gcs-server", FAKE_GCS_TAG)
            .with_exposed_port(FAKE_GCS_PORT.tcp())
            .with_wait_for(WaitFor::http(
                HttpWaitStrategy::new("/storage/v1/b").with_expected_status_code(200_u16),
            ))
            .with_cmd(["-scheme", "http", "-port", &FAKE_GCS_PORT.to_string()])
            .start()
            .await
            .unwrap_or_else(|err| {
                panic!("failed to start fake-gcs-server; is Docker running? {err}")
            });

        let host = container.get_host().await.expect("container host");
        let port = container
            .get_host_port_ipv4(FAKE_GCS_PORT.tcp())
            .await
            .expect("fake-gcs-server port is mapped");
        let endpoint = Url::parse(&format!("http://{host}:{port}")).expect("valid endpoint URL");
        let bucket = Self {
            http: Client::new(),
            endpoint,
            _container: container,
        };

        bucket
            .http
            .post(bucket.url(&["storage", "v1", "b"]))
            .json(&json!({ "name": BUCKET }))
            .send()
            .await
            .expect("fake-gcs-server is unreachable")
            .error_for_status()
            .expect("fake-gcs-server failed to create the bucket");
        bucket
    }

    /// Writes `body` to `object`, replacing any existing object.
    pub(crate) async fn put(&self, object: &str, content_type: &str, body: Vec<u8>) {
        self.http
            .post(self.url(&["upload", "storage", "v1", "b", BUCKET, "o"]))
            .query(&[("uploadType", "media"), ("name", object)])
            .header(reqwest::header::CONTENT_TYPE, content_type)
            .body(body)
            .send()
            .await
            .expect("fake-gcs-server is unreachable")
            .error_for_status()
            .unwrap_or_else(|err| panic!("failed to write {object:?}: {err}"));
    }

    /// Reads the content of `object`.
    pub(crate) async fn get(&self, object: &str) -> Vec<u8> {
        self.http
            .get(self.url(&["storage", "v1", "b", BUCKET, "o", object]))
            .query(&[("alt", "media")])
            .send()
            .await
            .expect("fake-gcs-server is unreachable")
            .error_for_status()
            .unwrap_or_else(|err| panic!("failed to read {object:?}: {err}"))
            .bytes()
            .await
            .expect("failed to read the response body")
            .to_vec()
    }

    /// Joins `segments` onto the endpoint. Each segment is percent-encoded on its own, so an
    /// object name such as `icons/a.png` stays one segment (`icons%2Fa.png`), as GCS expects.
    fn url(&self, segments: &[&str]) -> Url {
        let mut url = self.endpoint.clone();
        url.path_segments_mut()
            .expect("an http URL has a path")
            .pop_if_empty()
            .extend(segments);
        url
    }
}
