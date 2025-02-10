
# Asycnchronous Python Google Cloud Storage Client

* Status: Accepted
* Deciders: Nan Jiang, Herraj Luhano
* Date: 2025-02-04

## Context and Problem Statement

The Merino application has expanded to include the `/manifest` endpoint that interacts with a Google Cloud Storage (GCS) bucket. Currently, Merino relies on the official Google Cloud Python client (`google-cloud-storage`) for interacting with GCS for weekly job runs, but this client is synchronous.

Since the `/manifest` endpoint handles requests in an asynchronous web environment, using a synchronous client would block the main thread, leading to performance issues. To work around this, we currently offload GCS operations to thread pool dedicated for running synchronous workloads, but this adds unnecessary complexity.

To simplify the implementation and fully leverage asynchronous capabilities, we are considering adopting `talkiq/gcloud-aio-storage`, a community-supported asynchronous Python client for Google Cloud Storage. This would allow us to perform GCS operations without blocking the main thread, leading to cleaner and more efficient code.

## Decision Drivers

1. Deteriorated performance due to `/manifest` requests blocking the main thread.
2. Additional complexity due to implementing custom logic for background tasks.

## Considered Options

* A. `gcloud-aio-storage`.
* B. `google-cloud-storage` (Existing official synchronous Python client).

## Decision Outcome

Chosen option:

**A**. `gcloud-aio-storage`

`gcloud-aio-storage` appears to be the most widely used community-supported async client for Google Cloud Storage. It has fairly decent documentation, is easy to set up and use, and aligns well with Merino’s asynchronous architecture. Adopting it will simplify integration while ensuring non-blocking GCS interactions in the `/manifest` endpoint.

### Positive Consequences

* **Seamless integration** with existing implementation and logic. As an async client, it comes with native async APIs to GCS, which substantially simplifies the usage of GCS in Merino. Particularly, no more offloading synchronous calls over to the thread pool.
* **Easy authentication** -- No extra steps needed for authentication. Uses the same logic as the exisiting sync client.
* **Provides other asynch clients as well** -- `gcloud-aio` library has modules for other Google Cloud entities such as `BigQuery`, `PubSub`, e.t.c, which will be useful in the future.

### Negative Consequences

* **The SDK api is slightly different to the official one** --  When it comes to wrapper classes and return types. Although, it supports the basic wrapper classes for entities such as `Blob` and `Bucket`, some of the types are more raw / basic. This could be seen as allowing for implementation flexibility, however, it does introduce some verbosity.
* **Not officially supported by Google** -- Relying on community contributors for support and updates. Will have to migrate to the official async one if/when Google releases one.
* **Two GCS clients** -- Merino will use both the async client for the web app mode, and the official sync client for Merino jobs, which might cause confusion.

## Pros and Cons of the Synchronous Client

#### Pros
*  **Officially Supported by Google** – Maintained and supported by Google, ensuring long-term reliability, security updates, and compatibility with GCS features.

*  **Official Documentation & Large User Base** – Extensive official documentation and a large user base, making it easier to find solutions to issues.

*  **Consistent with Existing Usage** – Already used in Merino’s jobs component, reducing the need to maintain multiple clients for the same service.

*  **No Additional Dependencies** – Avoids adding a third-party dependency, reducing potential maintenance overhead.

#### Cons
* **Blocks the Main Thread** – The client is synchronous, which can lead to performance issues in Merino’s `/manifest` endpoint by blocking request handling.

* **Workarounds Add Complexity** – Using background tasks to offload GCS operations introduces unnecessary complexity and potential race conditions.

* **Inconsistent with Merino’s Async Architecture** – Merino is built to be asynchronous, and using a sync client requires special handling, breaking architectural consistency.

* **Potential Scalability Issues** – Blocking I/O operations can slow down request processing under high load, reducing overall efficiency.

* **Misses Out on Async Benefits** – Async clients improve responsiveness and throughput by allowing other tasks to execute while waiting for network responses.

## Links

* [Github repo for talkiq/gcloud-aio](https://github.com/talkiq/gcloud-aio)
