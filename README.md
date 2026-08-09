# Home Lab

Hi, I'm Diego and this is a repo explaining my home lab, a Raspberry Pi 4 and an Asrock Deskmini 110 running self-hosted services and APIs I built and maintain.

It started as a kid's dream of running my own server, blocked at the time by my ISP's port-forwarding restrictions. Today it's my hands-on lab for networking, system administration, and self-hosting; DNS, reverse proxying, tunneling, cron-based automation, backups, and running services I'd otherwise pay for.

## Architecture

![Diagram](./diagrams/architecture.png)

This lab runs across two physical machines:
- **Raspberry Pi 4 (4GB)** $\longrightarrow$ hosts the bulk of services, organized into four layers: *network* (DNS, reverse proxy, DDNS), the *Character Gallery API*, *observability* and *automation*. 
- Asrock Deskmini 110 $\longrightarrow$ runs the *Minecraft server* and will host cross-server database backups (*persistance* layer). Configured with NixOS.

The workload is split by resource profile: the Pi's 4GB of RAM comfortably handles the containerized services below (mostly I/O-bound: DNS, proxying, lightweight APIs), while Minecraft's memory and uptime demands run better isolated on the Deskmini, dedicated hardware, no contention with anything else.

### Network Design

Services are split across two isolated Docker networks by function: `dragored` for backend/data services, and `proxy_net` for anything fronted by **nginx**. Exposure is asymmetric:
- **Public**: Minecraft server (via DDNS, since friends connect directly) and select services proxied through a Cloudflare Tunnel.
- **Internal Only**: everything else (Grafana, Prometheus, Adguard's UI) is reachable via internal DNS rewrites in Adguard, only resolvable on the local network and not exposed to the internet.

This keeps the attack surface small: only those services that need exposure are exposed, and everything is not exposed by default.

## Services

| Service                          | Purpose                             | Stack                                    | Docs                                                   |
| -------------------------------- | ----------------------------------- | ---------------------------------------- | ------------------------------------------------------ |
| character-gallery-api            | RPG characters CRUD API             | Go, Postgres, Redis, JWT, GitHub Actions | [repo](https://www.github.com/dZev1/character-gallery) |
| adguard                          | DNS + ad blocking                   | AdguardHome, DoQ                         | [docs](docs/networking.md)                             |
| nginx                            | Reverse proxy                       | nginx                                    | [docs](docs/networking.md)                             |
| ddns-updater                     | Dynamic DNS for my minecraft server | ddns-updater                             | [docs](docs/networking.md)                             |
| grafana / prometheus / exporters | Observability                       | Grafana, Prometheus                      | [docs](docs/monitoring.md)                             |
| n8n                              | Workflow automation                 | n8n                                      | —                                                      |
| minecraft-server                 | Server for my friends               | Fabric, NixOS                            | [docs](docs/minecraft-server.md)                       |

## Technical Highlights

- Own API written in Go with JWT, rate limiting, cache in Redis
- Network segmentation per function (isolated Docker networks)
- Internal DNS vs. Selective public exposure via Cloudflare Tunnel
- Declarative NixOS configuration on second server (IaC)
- Automated backups with real verification (proven restores)
- Pre-loaded world chunks to reduce CPU load on limited hardware (Celeron)

## Project Status

**Implemented**

- Minecraft backups (with detected and corrected incident, see `docs` for more info)
- Complete system and DB Monitoring
- Declarative config on NixOS server

**Pending**

- cross-server backups for Postgres (RPi → Deskmini via `pg_dump + scp`)
- Restricted SSH keys with `command=` for said backup

## General Stack

- **Docker Compose** for each service
- **NixOS** (IaC) in the Deskmini
- **Cloudflare Tunnel**
- Reverse Proxy with **nginx**
- Monitoring with **Grafana** & **Prometheus**

## Repo Structure

```
docker-compose/ ← sanitized copies of each service
docs/ ← detailed documentation per area
nix/ ← sanitized excerpt of the Deskmini's configuration.nix
diagrams/ ← architecture diagram.
```
