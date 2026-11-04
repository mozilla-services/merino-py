//! Batch commands run by CronJobs and Jobs: scrape, import, and later sync and cleanup.
//!
//! May depend on `catalog`, `scraper`, `domain` and `config`. Each job returns an error on
//! failure, so that `main` exits non-zero and Kubernetes records the run as failed.
