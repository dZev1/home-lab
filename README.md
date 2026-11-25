# Home Lab

Hi, I'm Diego and this is a repo explaining my home lab: three Linux nodes (a Raspberry Pi 4, an Asrock Deskmini 110, and a Mac Mini) running self-hosted services, media, Git hosting, and APIs I built and maintain.

It started as a kid's dream of running my own server, blocked at the time by my ISP's port-forwarding restrictions. Today it's my hands-on lab for networking, system administration, and self-hosting; DNS, reverse proxying, tunneling, cron/systemd automation, backups, and running services I'd otherwise pay for.

## Architecture

![Diagram](./diagrams/architecture.png)

This lab runs across three physical Linux machines:

<!-- AUTO:NODES:START -->
| Node | Role | OS / Arch | Hardware | Host Services |
| ---- | ---- | --------- | -------- | ------------- |
| **Asrock Deskmini 110** (`deskmini`) | Minecraft Server & Cross-Server Backups | `Debian` *(pending sync)* | — | — |
| **Mac Mini** (`mac-mini`) | Media Server | `Debian GNU/Linux 13 (trixie)` (`x86_64`) | 4c · 7.6 GB RAM · 210.3 GB disk | `Docker`, `Jellyfin`, `OpenSSH`, `WireGuard` |
| **rpi-4** (`rpi-4`) | Networking node | `Debian GNU/Linux 13 (trixie)` (`aarch64`) | 4c · 3.7 GB RAM · 916.3 GB disk | `Docker`, `OpenSSH`, `Tailscale` |
| **Raspberry Pi 4 (4GB)** (`rpi4`) | Networking, APIs, Observability & Automation | `Debian` *(pending sync)* | — | — |
<!-- AUTO:NODES:END -->

The workload is split by resource profile: the Pi's 4GB of RAM comfortably handles lightweight containerized services (mostly I/O-bound: DNS, proxying, APIs, observability), the Deskmini (Debian) isolates the Minecraft server and cross-server backups, and the Mac Mini (Debian) acts as a dedicated Media & Git Server (Forgejo, Jellyfin, Kavita, etc.).

### Network Design

Services are split across two isolated Docker networks by function: `dragored` for backend/data services, and `proxy_net` for anything fronted by **nginx**. Exposure is asymmetric:
- **Public**: Minecraft server (via DDNS, since friends connect directly) and select services proxied through a Cloudflare Tunnel.
- **Internal Only**: everything else (Grafana, Prometheus, Adguard's UI) is reachable via internal DNS rewrites in Adguard, only resolvable on the local network and not exposed to the internet.

This keeps the attack surface small: only those services that need exposure are exposed, and everything is not exposed by default.

<!-- AUTO:TOPOLOGY:START -->
<details>
<summary><strong>Auto-generated Multi-Node Topology Diagram (Mermaid)</strong></summary>

```mermaid
flowchart LR
  subgraph node_deskmini["Asrock Deskmini 110 (Debian)"]
    info_deskmini["Minecraft Server & Cross-Server Backups"]
  end
  subgraph node_mac_mini["Mac Mini — Debian GNU/Linux 13 (trixie)"]
    hs_mac-mini_0["host: Docker"]
    hs_mac-mini_1["host: Jellyfin"]
    hs_mac-mini_2["host: OpenSSH"]
    hs_mac-mini_3["host: WireGuard"]
    tm_mac-mini_0["timer: homelab-docs (*-*-* 04:00:00)"]
  end
  subgraph node_rpi_4["rpi-4 — Debian GNU/Linux 13 (trixie)"]
    hs_rpi-4_0["host: Docker"]
    hs_rpi-4_1["host: OpenSSH"]
    hs_rpi-4_2["host: Tailscale"]
  end
  subgraph node_rpi4["Raspberry Pi 4 (4GB) (Debian)"]
    net_rpi4_bridge{{"bridge"}}
    net_rpi4_default__bridge_{{"default (bridge)"}}
    net_rpi4_dragored{{"dragored"}}
    net_rpi4_proxy_net{{"proxy_net"}}
    svc_rpi4_adguard_home["adguard-home (adguard)"]
    svc_rpi4_adguard_home --- net_rpi4_proxy_net
    svc_rpi4_character_gallery_api["character-gallery-api"]
    svc_rpi4_character_gallery_api --- net_rpi4_dragored
    svc_rpi4_character_gallery_api --- net_rpi4_proxy_net
    svc_rpi4_cloudflared["cloudflared (cloudflare-tunnel)"]
    svc_rpi4_cloudflared --- net_rpi4_dragored
    svc_rpi4_ddns_updater["ddns-updater"]
    svc_rpi4_ddns_updater --- net_rpi4_bridge
    svc_rpi4_grafana["grafana"]
    svc_rpi4_grafana --- net_rpi4_proxy_net
    svc_rpi4_kavita["kavita (kavita-server)"]
    svc_rpi4_kavita --- net_rpi4_proxy_net
    svc_rpi4_n8n["n8n"]
    svc_rpi4_n8n --- net_rpi4_dragored
    svc_rpi4_nginx["nginx (nginx-proxy)"]
    svc_rpi4_nginx --- net_rpi4_proxy_net
    svc_rpi4_node_exporter["node-exporter"]
    svc_rpi4_node_exporter --- net_rpi4_proxy_net
    svc_rpi4_postgres["postgres (postgres-server)"]
    svc_rpi4_postgres --- net_rpi4_dragored
    svc_rpi4_postgres_exporter["postgres-exporter"]
    svc_rpi4_postgres_exporter --- net_rpi4_proxy_net
    svc_rpi4_postgres_exporter --- net_rpi4_dragored
    svc_rpi4_prometheus["prometheus"]
    svc_rpi4_prometheus --- net_rpi4_proxy_net
    svc_rpi4_redis["redis (redis-cache)"]
    svc_rpi4_redis --- net_rpi4_default__bridge_
  end
  svc_rpi4_nginx -. "HTTPS adguard.domain" .-> svc_rpi4_adguard_home
  svc_rpi4_nginx -. "HTTPS grafana.domain" .-> svc_rpi4_grafana
  svc_rpi4_nginx -. "HTTPS prometheus.domain" .-> svc_rpi4_prometheus
  svc_rpi4_nginx -. "HTTPS kavita.domain" .-> svc_rpi4_kavita
  svc_rpi4_prometheus -. "scrape" .-> svc_rpi4_node_exporter
  svc_rpi4_prometheus -. "scrape" .-> svc_rpi4_character_gallery_api
  svc_rpi4_prometheus -. "scrape" .-> svc_rpi4_postgres_exporter
```

</details>
<!-- AUTO:TOPOLOGY:END -->

## Services

<!-- AUTO:SERVICES:START -->
| Node | Service | Image / Stack | Networks | Purpose | Docs |
| ---- | ------- | ------------- | -------- | ------- | ---- |
| `rpi4` | `adguard-home` | `adguard/adguardhome` | `proxy_net` | Internal DNS + ad blocking (DoQ) | [docs](docs/networking.md) |
| `rpi4` | `character-gallery-api` | `character-gallery-api:latest` | `dragored`, `proxy_net` | RPG characters CRUD API (Go) | [repo](https://github.com/dZev1/character-gallery-api) |
| `rpi4` | `cloudflared` | `cloudflare/cloudflared:latest` | `dragored` | Selective public exposure without open ports | [docs](docs/networking.md) |
| `rpi4` | `ddns-updater` | `ghcr.io/qdm12/ddns-updater` | `bridge` | Dynamic DNS updater for Minecraft server | [docs](docs/networking.md) |
| `rpi4` | `grafana` | `grafana/grafana-oss` | `proxy_net` | Dashboards & observability UI | [docs](docs/monitoring.md) |
| `rpi4` | `kavita` | `jvmilazz0/kavita:latest` | `proxy_net` | Self-hosted e-book & university notes reader | [compose](docker-compose/kavita/compose.yaml) |
| `rpi4` | `n8n` | `n8nio/n8n:latest` | `dragored` | Workflow automation | [compose](docker-compose/n8n/compose.yaml) |
| `rpi4` | `nginx` | `nginx:stable-alpine3.24-perl` | `proxy_net` | TLS reverse proxy for internal services | [docs](docs/networking.md) |
| `rpi4` | `node-exporter` | `prom/node-exporter` | `proxy_net` | Host OS & hardware metrics exporter | [docs](docs/monitoring.md) |
| `rpi4` | `postgres` | `arm64v8/postgres:18.4-alpine3.23` | `dragored` | Primary relational database (API & n8n) | [compose](docker-compose/postgres/compose.yaml) |
| `rpi4` | `postgres-exporter` | `prometheuscommunity/postgres-exporter` | `proxy_net`, `dragored` | PostgreSQL metrics exporter for Prometheus | [docs](docs/monitoring.md) |
| `rpi4` | `prometheus` | `prom/prometheus:main` | `proxy_net` | Time-series metrics collection | [docs](docs/monitoring.md) |
| `rpi4` | `redis` | `redis:alpine` | `default (bridge)` | In-memory cache & rate limiting | [compose](docker-compose/redis/compose.yaml) |
| `deskmini` | `minecraft-server` | `Fabric, Debian (systemd backups)` | `host` | Private Minecraft server for friends | [docs](docs/minecraft-server.md) |

> *Auto-generated from `nodes/*.json` and `docker-compose/*/compose.yaml` via `scripts/generate_docs.py`. See [`docs/inventory.md`](docs/inventory.md) for full hardware specs, ports, NGINX routes, Prometheus targets, and systemd timers.*
<!-- AUTO:SERVICES:END -->

## Technical Highlights

- Own API written in Go with JWT, rate limiting, cache in Redis
- Multi-node Linux setup (Raspberry Pi 4 + Deskmini + Mac Mini on Debian)
- Network segmentation per function (isolated Docker networks)
- Internal DNS vs. Selective public exposure via Cloudflare Tunnel
- Automated backups with real verification (proven restores)
- Pre-loaded world chunks to reduce CPU load on limited hardware (Celeron)
- Automated Docs-as-Code pipeline (per-node snapshot collectors + GitHub Actions)

## Project Status

**Implemented**

- Minecraft backups (with detected and corrected incident, see `docs` for more info)
- Complete system and DB Monitoring
- Dedicated Media & Git Server on Mac Mini (Debian)
- Automated multi-node inventory & topology documentation

**Pending**

- cross-server backups for Postgres (RPi → Deskmini via `pg_dump + scp`)
- Restricted SSH keys with `command=` for said backup

## General Stack

- **Debian / Linux** across all nodes
- **Docker Compose** for containerized services
- **Cloudflare Tunnel**
- Reverse Proxy with **nginx**
- Monitoring with **Grafana** & **Prometheus**
- **GitHub Actions** for automated Docs-as-Code inventory

## Repo Structure

```
nodes/ ← sanitized per-node JSON snapshots pushed automatically by each server
docker-compose/ ← sanitized copies of each service
docs/ ← detailed documentation per area + auto-generated inventory
diagrams/ ← architecture diagram
scripts/ ← node collector, sync script, systemd templates & docs generator
```
