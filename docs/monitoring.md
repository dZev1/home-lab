# Monitoring

## Overview

System and application metrics are collected with Prometheus and
visualized in Grafana, covering both infrastructure-level health
(CPU, memory, disk) and application-level behavior (request latency,
error rates) for the Character Gallery API.

## Stack

- **Prometheus** - scrapes and stores metrics as time series, on a
  30s scrape interval.
- **Grafana** - dashboards built on top of Prometheus as a data
  source.
- **node-exporter** - exposes host-level metrics (CPU, memory, disk,
  network) from the Raspberry Pi itself.
- **postgres-exporter** - exposes PostgreSQL metrics (connections,
  query performance, database size).
- **Custom `/metrics` endpoint** - instrumented directly in the
  Character Gallery API (Go), exposing request latency, error rate,
  and throughput for scraping.

## Scrape Targets

```yaml
scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]
  - job_name: "node-exporter"
    static_configs:
      - targets: ["node-exporter:9100"]
  - job_name: "character_gallery"
    static_configs:
      - targets: ["character-gallery-api:8080"]
  - job_name: "postgres-db"
    static_configs:
      - targets: ["postgres-exporter:9187"]
```

## Network Design Note

Prometheus and most exporters live on `proxy_net`, but the services
they scrape data from (Postgres, the Character Gallery API) live on
`dragored`. Both `postgres-exporter` and `character-gallery-api` are
explicitly attached to both networks so Prometheus can resolve and
reach them. See [networking.md](./networking.md#network-segmentation-docker)
for the full network segmentation design.

## Access

- Grafana and Prometheus are reachable only via internal DNS rewrites
  in Adguard (`grafana.dezetin.com`, `prometheus.dezetin.com`),
  fronted by NGINX with TLS, not exposed to the internet.
- Grafana admin credentials are set via environment variables, not
  hardcoded.

## Why Application-Level Metrics Matter

Instrumenting the Character Gallery API directly (rather than only
relying on infrastructure metrics) makes it possible to see problems
that host-level metrics alone would miss. For instance, a slow endpoint or
rising error rate wouldn't necessarily show up as a CPU or memory
spike on the Pi.

## Roadmap

- Alerting (e.g. Alertmanager) for critical failures. Currently,
  problems are found by manually checking dashboards rather than
  being pushed as alerts.
- This gap is directly related to two incidents documented elsewhere
  in this repo (silent backup failure, silent DDNS failure) that went
  undetected because nothing actively monitored for them:
  - [Minecraft backup incident](./minecraft-server.md#incident-silent-backup-failure)
  - [DDNS incident](./networking.md#incident-silent-ddns-failure)
- `auth_basic` on Prometheus/Grafana as defense in depth.
