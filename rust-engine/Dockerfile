FROM rust:1.85-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*

COPY Cargo.toml Cargo.lock* ./
# Create dummy main to cache dependencies
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo update 2>/dev/null || true && \
    cargo update time@0.3.47 --precise 0.3.36 2>/dev/null || true && \
    cargo update time-core@0.1.8 --precise 0.1.2 2>/dev/null || true && \
    cargo build --release 2>/dev/null || true

COPY src ./src
RUN touch src/main.rs && cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/nexquant-engine /usr/local/bin/

EXPOSE 8080
CMD ["nexquant-engine"]
