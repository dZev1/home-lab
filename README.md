# Home Lab

Hi, I'm Diego and this is a repo explaining my home lab: three Linux nodes (a Raspberry Pi 4, an Asrock Deskmini 110, and a Mac Mini) running self-hosted services, media, Git hosting, and APIs I built and maintain.

It started as a kid's dream of running my own server, blocked at the time by my ISP's port-forwarding restrictions. Today it's my hands-on lab for networking, system administration, and self-hosting; DNS, reverse proxying, tunneling, cron/systemd automation, backups, and running services I'd otherwise pay for.

## Architecture

![Diagram](./diagrams/architecture.png)

This lab runs across three physical Linux machines:

<!-- AUTO:NODES:START -->
| Node | Role | OS / Arch | Hardware | Host Services |
| ---- | ---- | --------- | -------- | ------------- |
| **Asrock Deskmini 110** (`deskmini`) | Backups and Minecraft | `Debian GNU/Linux 13 (trixie)` (`x86_64`) | 2c · 11.4 GB RAM · 431.5 GB disk | `Docker`, `OpenSSH`, `UFW Firewall` |
| **Mac Mini** (`mac-mini`) | Media Server | `Debian GNU/Linux 13 (trixie)` (`x86_64`) | 4c · 7.6 GB RAM · 210.3 GB disk | `Docker`, `Jellyfin`, `OpenSSH`, `WireGuard` |
| **Raspberry Pi 4 (4GB)** (`rpi-4`) | Networking node | `Debian GNU/Linux 13 (trixie)` (`aarch64`) | 4c · 3.7 GB RAM · 916.3 GB disk | `Docker`, `OpenSSH`, `Tailscale` |
| **rpi4** (`rpi4`) | Networking | `Debian GNU/Linux 13 (trixie)` (`aarch64`) | 4c · 3.7 GB RAM · 916.3 GB disk | `Docker`, `OpenSSH`, `Tailscale` |
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
  subgraph node_deskmini["Asrock Deskmini 110 — Debian GNU/Linux 13 (trixie)"]
    net_deskmini_monitoring_default{{"monitoring_default"}}
    net_deskmini_outerwilds{{"outerwilds"}}
    svc_deskmini_node_exporter["node-exporter"]
    svc_deskmini_node_exporter --- net_deskmini_monitoring_default
    svc_deskmini_postgres["postgres"]
    svc_deskmini_postgres --- net_deskmini_outerwilds
    svc_deskmini_redis["redis (redis-cache)"]
    svc_deskmini_redis --- net_deskmini_outerwilds
    hs_deskmini_1["host: OpenSSH"]
    hs_deskmini_2["host: UFW Firewall"]
    tm_deskmini_0["timer: homelab-docs (*-*-* 04:00:00)"]
  end
  subgraph node_mac_mini["Mac Mini — Debian GNU/Linux 13 (trixie)"]
    net_mac_mini_forgejo_default{{"forgejo_default"}}
    net_mac_mini_kavita_default{{"kavita_default"}}
    net_mac_mini_monitoring_default{{"monitoring_default"}}
    svc_mac_mini_forgejo["forgejo"]
    svc_mac_mini_forgejo --- net_mac_mini_forgejo_default
    svc_mac_mini_kavita["kavita (kavita-server)"]
    svc_mac_mini_kavita --- net_mac_mini_kavita_default
    svc_mac_mini_node_exporter["node-exporter"]
    svc_mac_mini_node_exporter --- net_mac_mini_monitoring_default
    hs_mac_mini_1["host: Jellyfin"]
    hs_mac_mini_2["host: OpenSSH"]
    hs_mac_mini_3["host: WireGuard"]
    tm_mac_mini_0["timer: homelab-docs (*-*-* 04:00:00)"]
  end
  subgraph node_rpi_4["Raspberry Pi 4 (4GB) — Debian GNU/Linux 13 (trixie)"]
    net_rpi_4_dragored{{"dragored"}}
    net_rpi_4_proxy_net{{"proxy_net"}}
    svc_rpi_4_n8n["n8n"]
    svc_rpi_4_n8n --- net_rpi_4_dragored
    svc_rpi_4_node_exporter["node-exporter"]
    svc_rpi_4_node_exporter --- net_rpi_4_proxy_net
    svc_rpi_4_postgres_exporter["postgres-exporter"]
    svc_rpi_4_postgres_exporter --- net_rpi_4_proxy_net
    svc_rpi_4_postgres_exporter --- net_rpi_4_dragored
    hs_rpi_4_1["host: OpenSSH"]
    hs_rpi_4_2["host: Tailscale"]
  end
  subgraph node_rpi4["rpi4 — Debian GNU/Linux 13 (trixie)"]
    net_rpi4_bridge{{"bridge"}}
    net_rpi4_dragored{{"dragored"}}
    net_rpi4_proxy_net{{"proxy_net"}}
    svc_rpi4_adguard_home["adguard-home (adguard)"]
    svc_rpi4_adguard_home --- net_rpi4_proxy_net
    svc_rpi4_character_gallery_api["character-gallery-api"]
    svc_rpi4_character_gallery_api --- net_rpi4_dragored
    svc_rpi4_cloudflared["cloudflared (cloudflare-tunnel)"]
    svc_rpi4_cloudflared --- net_rpi4_dragored
    svc_rpi4_ddns_updater["ddns-updater"]
    svc_rpi4_ddns_updater --- net_rpi4_bridge
    svc_rpi4_grafana["grafana"]
    svc_rpi4_grafana --- net_rpi4_proxy_net
    svc_rpi4_nginx["nginx (nginx-proxy)"]
    svc_rpi4_nginx --- net_rpi4_proxy_net
    svc_rpi4_node_exporter["node-exporter"]
    svc_rpi4_node_exporter --- net_rpi4_proxy_net
    svc_rpi4_portainer["portainer"]
    svc_rpi4_portainer --- net_rpi4_bridge
    svc_rpi4_prometheus["prometheus"]
    svc_rpi4_prometheus --- net_rpi4_dragored
    svc_rpi4_prometheus --- net_rpi4_proxy_net
    svc_rpi4_vaultwarden["vaultwarden"]
    svc_rpi4_vaultwarden --- net_rpi4_proxy_net
    hs_rpi4_1["host: OpenSSH"]
    hs_rpi4_2["host: Tailscale"]
    tm_rpi4_0["timer: homelab-docs (*-*-* 04:00:00)"]
  end
  svc_rpi4_nginx -. "HTTPS adguard.domain" .-> svc_rpi4_adguard_home
  svc_rpi4_nginx -. "HTTPS grafana.domain" .-> svc_rpi4_grafana
  svc_rpi4_nginx -. "HTTPS prometheus.domain" .-> svc_rpi4_prometheus
  svc_rpi4_nginx -. "HTTPS kavita.domain" .-> svc_mac_mini_kavita
  svc_rpi4_prometheus -. "scrape" .-> svc_rpi4_node_exporter
  svc_rpi4_prometheus -. "scrape" .-> svc_rpi4_character_gallery_api
  svc_rpi4_prometheus -. "scrape" .-> svc_rpi_4_postgres_exporter
```

</details>
<!-- AUTO:TOPOLOGY:END -->

## Services

<!-- AUTO:SERVICES:START -->
| Node | Service | Image / Stack | Networks | Purpose | Docs |
| ---- | ------- | ------------- | -------- | ------- | ---- |
| `deskmini` | `node-exporter` | `prom/node-exporter` | `monitoring_default` | Host OS & hardware metrics exporter | [docs](docs/monitoring.md) |
| `deskmini` | `postgres` | `postgres:18.4-alpine3.23` | `outerwilds` | Primary relational database (API & n8n) | [compose](docker-compose/postgres/compose.yaml) |
| `deskmini` | `redis` | `redis:alpine` | `outerwilds` | In-memory cache & rate limiting | [compose](docker-compose/redis/compose.yaml) |
| `mac-mini` | `forgejo` | `codeberg.org/forgejo/forgejo:15` | `forgejo_default` | Self-hosted Git forge | — |
| `mac-mini` | `kavita` | `jvmilazz0/kavita:latest` | `kavita_default` | Self-hosted e-book & university notes reader | [docs](docs/networking.md) |
| `mac-mini` | `node-exporter` | `prom/node-exporter` | `monitoring_default` | Host OS & hardware metrics exporter | [docs](docs/monitoring.md) |
| `rpi-4` | `n8n` | `n8nio/n8n:latest` | `dragored` | Workflow automation | [compose](docker-compose/n8n/compose.yaml) |
| `rpi-4` | `node-exporter` | `prom/node-exporter` | `proxy_net` | Host OS & hardware metrics exporter | [docs](docs/monitoring.md) |
| `rpi-4` | `postgres-exporter` | `prometheuscommunity/postgres-exporter` | `proxy_net`, `dragored` | PostgreSQL metrics exporter for Prometheus | [docs](docs/monitoring.md) |
| `rpi4` | `adguard-home` | `adguard/adguardhome` | `proxy_net` | Internal DNS + ad blocking (DoQ) | [docs](docs/networking.md) |
| `rpi4` | `character-gallery-api` | `character-gallery-api:latest` | `dragored` | RPG characters CRUD API (Go) | [repo](https://github.com/dZev1/character-gallery-api) |
| `rpi4` | `cloudflared` | `cloudflare/cloudflared:latest` | `dragored` | Selective public exposure without open ports | [docs](docs/networking.md) |
| `rpi4` | `ddns-updater` | `ghcr.io/qdm12/ddns-updater` | `bridge` | Dynamic DNS updater for Minecraft server | [docs](docs/networking.md) |
| `rpi4` | `grafana` | `grafana/grafana-oss` | `proxy_net` | Dashboards & observability UI | [docs](docs/monitoring.md) |
| `rpi4` | `nginx` | `nginx:1.30.7-alpine3.24` | `proxy_net` | TLS reverse proxy for internal services | [docs](docs/networking.md) |
| `rpi4` | `node-exporter` | `prom/node-exporter` | `proxy_net` | Host OS & hardware metrics exporter | [docs](docs/monitoring.md) |
| `rpi4` | `portainer` | `portainer/portainer-ce:lts` | `bridge` | — | — |
| `rpi4` | `prometheus` | `prom/prometheus:main` | `dragored`, `proxy_net` | Time-series metrics collection | [docs](docs/monitoring.md) |
| `rpi4` | `vaultwarden` | `vaultwarden/server:testing` | `proxy_net` | — | — |
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
