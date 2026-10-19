# Upstream no longer serves these community images from Docker Hub/Quay.
# Build the pinned upstream releases instead of relying on a third-party image.
FROM golang:1.24-bookworm AS server-build
ARG MINIO_VERSION=RELEASE.2025-04-22T22-12-26Z
RUN git clone --depth 1 --branch ${MINIO_VERSION} https://github.com/minio/minio.git /src
WORKDIR /src
RUN CGO_ENABLED=0 GOMAXPROCS=2 go build -p 2 -trimpath -o /out/minio .

FROM golang:1.24-bookworm AS client-build
ARG MC_VERSION=RELEASE.2025-04-16T18-13-26Z
RUN git clone --depth 1 --branch ${MC_VERSION} https://github.com/minio/mc.git /src
WORKDIR /src
RUN CGO_ENABLED=0 GOMAXPROCS=2 go build -p 2 -trimpath -o /out/mc .

FROM debian:bookworm-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*

FROM base AS server
COPY --from=server-build /out/minio /usr/local/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]

FROM base AS client
COPY --from=client-build /out/mc /usr/local/bin/mc
ENTRYPOINT ["mc"]
