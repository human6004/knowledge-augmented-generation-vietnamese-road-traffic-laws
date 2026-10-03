# Build the patched official source release instead of the older prebuilt image.
FROM golang:1.24.8-bookworm AS build
ENV CGO_ENABLED=0
RUN go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* && useradd --system --uid 10001 minio && mkdir /data && chown minio /data
COPY --from=build /go/bin/minio /usr/local/bin/minio
USER 10001
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
