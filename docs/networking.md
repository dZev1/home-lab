# Networking

## Overview

Network-facing services run on the Raspberry Pi 4 and handle DNS,
reverse proxying, dynamic DNS, and secure external exposure. Design
follows a simple principle: nothing is exposed by default. Each
service earns its exposure based on an actual need.

## DNS — Adguard Home

- Acts as the internal DNS server for the home network, blocking ads
  and trackers at the DNS level.
- Uses **DNS-over-QUIC (DoQ)** for queries from the network, with
  internal caching on the server for repeated lookups.
- Also handles internal DNS rewrites for `*.dezetin.com` subdomains
  (e.g. `grafana.dezetin.com`, `prometheus.dezetin.com`), resolving
  them only within the local network — these are never reachable from
  the internet.

### DHCP limitation and workaround

- Attempted to configure Adguard as a DHCP server to apply DNS
  filtering network-wide automatically.
- Blocked by the ISP's router, which doesn't allow disabling its own
  DHCP server.
- Workaround: DNS is configured manually per device instead of
  network-wide. Less convenient, but keeps ad/tracker blocking
  functional for every device it's set up on.

## Reverse Proxy — NGINX

- Routes traffic to internal services based on subdomain
  (`server_name`), terminating TLS with Let's Encrypt certificates.
- Certificates renewed automatically via a cronjob running `certbot`.
- Refactored to use **reusable snippets** (`include`) for repeated
  proxy headers instead of duplicating them across every
  `server {}` block:
  - `proxy-common.conf`, base headers (`Host`, `X-Real-IP`,
    `X-Forwarded-For`, `X-Forwarded-Proto`), included in every service.
  - `proxy-websocket.conf`, WebSocket/SSE support (`Upgrade`,
    `Connection`), included only where needed (Adguard UI, Grafana,
    Kavita).
- This cut the config from ~55 lines of repeated headers down to a few
  lines per service, and makes adding a new proxied service faster and
  less error-prone.

## Dynamic DNS — ddns-updater

- The ISP changes the home's public IP roughly weekly, which would
  otherwise break external access to services that need it, most
  notably the Minecraft server (see
  [minecraft-server.md](minecraft-server.md)).
- `ddns-updater` runs on a schedule (`PERIOD=5m`) and keeps the
  `play.dezetin.com` record pointed at the current public IP.

### Incident: Silent DDNS Failure

- The DNS record for `play.dezetin.com` stopped updating for a full
  week without any visible failure, friends couldn't connect to the
  Minecraft server until the issue was noticed.
- Root cause: incorrect DNS provider configuration in `ddns-updater`,
  causing update attempts to silently fail.
- Why it went undetected: the container's healthcheck only validates
  general internet connectivity (`wget --spider https://1.1.1.1`), not
  that the DNS record itself was successfully updated — so the
  container reported `healthy` all week despite the core function
  being broken.
- Fix: corrected the provider configuration.

## External Exposure — Cloudflare Tunnel

- `cloudflared` connects the Raspberry Pi to Cloudflare via an
  outbound tunnel, avoiding the need for any port-forwarding on the
  router.
- Only services that specifically need public access are routed
  through the tunnel (e.g. the Character Gallery API). Everything
  else stays internal-only via Adguard's DNS rewrites.
- SSL/TLS and DNS management for exposed subdomains are handled on
  Cloudflare's side.

## Network Segmentation (Docker)

Services are split across two isolated Docker networks by function:

- **`dragored`** — backend/data services (Postgres, Redis, the
  Character Gallery API, n8n, Cloudflare Tunnel).
- **`proxy_net`** — anything fronted by NGINX (Adguard's UI, Grafana,
  Prometheus, Kavita).

Some services (like `postgres-exporter`) need to bridge both networks
to reach a data service and be scraped by Prometheus. This is
declared explicitly rather than left as an accident of default Docker
networking.

## Roadmap

- Healthcheck for `ddns-updater` that validates the actual DNS record,
  not just internet connectivity.
- `auth_basic` on internally-exposed services as defense in depth,
  even though they aren't reachable from outside the local network
  today.
