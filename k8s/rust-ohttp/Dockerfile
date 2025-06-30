FROM rust:1.82 as builder

RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone https://github.com/martinthomson/ohttp.git
WORKDIR /app/ohttp

RUN cargo build --bin ohttp-server --release

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/ohttp/target/release/ohttp-server /usr/local/bin/
COPY --from=builder /app/ohttp/ohttp-server /opt/ohttp-server/

# Copy pre-generated certificates and config
COPY certs/ /opt/ohttp-server/

WORKDIR /opt/ohttp-server

EXPOSE 9443

# Fixed command with proper arguments
CMD ["ohttp-server", "0.0.0.0:9443", "-c", "/opt/ohttp-server/server.crt", "-k", "/opt/ohttp-server/server.key"]
