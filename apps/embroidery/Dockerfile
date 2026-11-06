# Build context: the repository root, as for every image in this repository (the docker-build
# task runs from the workspace root). Dockerfile.dockerignore narrows it to what this crate needs.

# The root rust-toolchain.toml selects the compiler, so the image and CI can't drift apart;
# the base image only provides rustup and a Debian 13 userland that matches the runtime below.
FROM rust:1-slim-trixie AS chef
WORKDIR /src
COPY rust-toolchain.toml ./
RUN rustup toolchain install && cargo install cargo-chef --version 0.1.78 --locked
# Keep the monorepo layout: the crate embeds ../../version.json with include_str!.
WORKDIR /src/apps/embroidery

FROM chef AS planner
COPY apps/embroidery/ ./
RUN cargo chef prepare --recipe-path recipe.json

FROM chef AS builder
COPY --from=planner /src/apps/embroidery/recipe.json recipe.json
# Dependencies compile in their own layer, which stays cached until Cargo.lock changes.
RUN cargo chef cook --release --locked --recipe-path recipe.json
# version.json changes on every CI run, so it comes after `cook` to keep the dependency layer.
COPY version.json /src/version.json
COPY apps/embroidery/ ./
RUN cargo build --release --locked --bin embroidery

# glibc, libgcc and CA certificates, which rustls and aws-lc-rs need; no shell.
FROM gcr.io/distroless/cc-debian13 AS runtime
COPY --from=builder /src/apps/embroidery/target/release/embroidery /app/embroidery
# Dockerflow expects UID 10001; distroless's own nonroot user is 65532.
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/app/embroidery"]
CMD ["serve"]
