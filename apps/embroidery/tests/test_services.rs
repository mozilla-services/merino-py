//! Smoke tests for the integration test containers: every test gets an empty database and a bucket
//! of its own. Tests of the real schema and blob store replace them once those exist.

#![allow(
    clippy::unwrap_used,
    reason = "test helpers panic on unexpected failures"
)]

mod common;

use common::{TestBucket, TestDb};

/// Fails if another test already created the table or wrote the row, which happens only if two
/// tests share a database.
async fn write_the_row_both_tests_write(db: &TestDb) {
    let pool = db.pool();
    sqlx::query("CREATE TABLE smoke (id integer PRIMARY KEY)")
        .execute(pool)
        .await
        .unwrap();
    sqlx::query("INSERT INTO smoke (id) VALUES (1)")
        .execute(pool)
        .await
        .unwrap();

    let rows: i64 = sqlx::query_scalar("SELECT count(*) FROM smoke")
        .fetch_one(pool)
        .await
        .unwrap();
    assert_eq!(rows, 1);
}

// nextest runs these two in parallel, each in its own process.
#[tokio::test]
async fn first_test_gets_its_own_database() {
    write_the_row_both_tests_write(&TestDb::start().await).await;
}

#[tokio::test]
async fn second_test_gets_its_own_database() {
    write_the_row_both_tests_write(&TestDb::start().await).await;
}

#[tokio::test]
async fn bucket_reads_back_written_object() {
    let bucket = TestBucket::create().await;

    bucket
        .put("icons/smoke.png", "image/png", b"fake png".to_vec())
        .await;

    assert_eq!(bucket.get("icons/smoke.png").await, b"fake png");
}
