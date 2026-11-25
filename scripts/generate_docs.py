#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Auto-generate multi-node Home Lab documentation from live node snapshots and repo configs.

Inputs:
  - nodes/*.json                         (sanitized snapshots pushed by each Linux node)
  - docker-compose/*/compose.yaml        (static compose fallback & config validation)
  - docker-compose/nginx/conf/services.conf
  - docker-compose/monitoring/prometheus.yaml
  - scripts/metadata.yaml                (optional human-readable descriptions)

Outputs:
  - docs/inventory.md                    (full auto-generated inventory & Mermaid topology)
  - README.md                            (in-place updates between AUTO marker comments)

Usage:
  python3 scripts/generate_docs.py
  python3 scripts/generate_docs.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
NODES_DIR = REPO_ROOT / "nodes"
COMPOSE_DIR = REPO_ROOT / "docker-compose"
NGINX_CONF = COMPOSE_DIR / "nginx" / "conf" / "services.conf"
PROMETHEUS_CONF = COMPOSE_DIR / "monitoring" / "prometheus.yaml"
METADATA_FILE = REPO_ROOT / "scripts" / "metadata.yaml"
README_FILE = REPO_ROOT / "README.md"
INVENTORY_FILE = REPO_ROOT / "docs" / "inventory.md"


@dataclass
class ServiceEntry:
    name: str
    node: str
    container_name: str
    image: str
    networks: list[str]
    ports: list[str]
    restart: str
    purpose: str
    docs: str
    source: str  # "live" or compose relative path
    status: str = "defined"


@dataclass
class NodeTimer:
    node: str
    name: str
    schedule: str
    description: str
    enabled: str = "enabled"


@dataclass
class NodeSnapshot:
    node: str
    display_name: str
    role: str
    os: str
    kernel: str
    arch: str
    cpu: str
    cpu_cores: int
    ram_gb: float
    root_disk_gb: float
    host_services: list[str] = field(default_factory=list)
    timers: list[NodeTimer] = field(default_factory=list)
    containers: list[ServiceEntry] = field(default_factory=list)


@dataclass
class NginxRoute:
    server_name: str
    upstream_host: str
    upstream_port: str
    ssl: bool
    websocket: bool


@dataclass
class PrometheusJob:
    job_name: str
    targets: list[str]


def load_metadata() -> dict[str, Any]:
    if not METADATA_FILE.exists():
        return {}
    return yaml.safe_load(METADATA_FILE.read_text(encoding="utf-8")) or {}


def normalize_networks(svc_cfg: dict[str, Any]) -> list[str]:
    if "network_mode" in svc_cfg:
        return [str(svc_cfg["network_mode"])]
    raw = svc_cfg.get("networks")
    if isinstance(raw, list):
        return [str(n) for n in raw]
    if isinstance(raw, dict):
        return [str(n) for n in raw.keys()]
    return ["default (bridge)"]


def normalize_ports(svc_cfg: dict[str, Any]) -> list[str]:
    raw = svc_cfg.get("ports") or []
    result: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            pub = entry.get("published", "")
            tgt = entry.get("target", "")
            proto = entry.get("protocol", "tcp")
            result.append(f"{pub}:{tgt}/{proto}")
        else:
            result.append(str(entry))
    return result


def parse_node_snapshots(meta: dict[str, Any]) -> list[NodeSnapshot]:
    if not NODES_DIR.exists():
        return []

    meta_nodes: dict[str, dict[str, str]] = meta.get("nodes") or {}
    meta_services: dict[str, dict[str, str]] = meta.get("services") or {}
    snapshots: list[NodeSnapshot] = []

    for json_path in sorted(NODES_DIR.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        node_key = str(data.get("node") or json_path.stem)
        node_meta = meta_nodes.get(node_key, {})
        sys_info = data.get("system") or {}

        timers = [
            NodeTimer(
                node=node_key,
                name=str(t.get("name", "unnamed")),
                schedule=str(t.get("schedule", "custom")),
                description=str(t.get("description", "—")),
                enabled=str(t.get("enabled", "unknown")),
            )
            for t in (data.get("systemd_timers") or [])
        ]

        containers: list[ServiceEntry] = []
        for c in data.get("docker_containers") or []:
            status = str(c.get("status", "unknown"))
            restart = str(c.get("restart", "no"))
            # Ignore one-off exited test containers (e.g. hello-world)
            if status == "exited" and restart == "no":
                continue
            svc_name = str(c.get("service") or c.get("container_name") or "unknown")
            container_name = str(c.get("container_name", svc_name))
            svc_meta = meta_services.get(svc_name) or meta_services.get(container_name) or {}
            containers.append(
                ServiceEntry(
                    name=svc_name,
                    node=node_key,
                    container_name=container_name,
                    image=str(c.get("image", "unknown")),
                    networks=[str(n) for n in (c.get("networks") or ["default"])],
                    ports=[str(p) for p in (c.get("ports") or [])],
                    restart=restart,
                    purpose=str(c.get("purpose") or svc_meta.get("purpose") or "—"),
                    docs=str(c.get("docs") or svc_meta.get("docs") or "—"),
                    source="live",
                    status=status,
                )
            )

        snapshots.append(
            NodeSnapshot(
                node=node_key,
                display_name=node_meta.get("display_name") or node_key,
                role=str(data.get("role") or node_meta.get("role") or "—"),
                os=str(sys_info.get("os", "Linux")),
                kernel=str(sys_info.get("kernel", "—")),
                arch=str(sys_info.get("arch", "—")),
                cpu=str(sys_info.get("cpu", "—")),
                cpu_cores=int(sys_info.get("cpu_cores") or 0),
                ram_gb=float(sys_info.get("ram_gb") or 0.0),
                root_disk_gb=float(sys_info.get("root_disk_gb") or 0.0),
                host_services=[str(s) for s in (data.get("host_services") or [])],
                timers=timers,
                containers=containers,
            )
        )

    return snapshots


def parse_compose_services(meta: dict[str, Any], default_node: str = "rpi-4") -> list[ServiceEntry]:
    services: list[ServiceEntry] = []
    meta_services: dict[str, dict[str, str]] = meta.get("services") or {}

    compose_files = sorted(
        list(COMPOSE_DIR.glob("*/compose.yaml"))
        + list(COMPOSE_DIR.glob("*/compose.yml"))
        + list(COMPOSE_DIR.glob("*/docker-compose.yaml"))
        + list(COMPOSE_DIR.glob("*/docker-compose.yml"))
    )

    for compose_path in compose_files:
        data = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
        rel_path = compose_path.relative_to(REPO_ROOT).as_posix()
        file_x_docs = data.get("x-docs") or {}

        for svc_name, svc_cfg in (data.get("services") or {}).items():
            if not isinstance(svc_cfg, dict):
                continue

            svc_x_docs = svc_cfg.get("x-docs") or {}
            svc_meta = meta_services.get(svc_name, {})

            purpose = (
                svc_x_docs.get("purpose")
                or file_x_docs.get("purpose")
                or svc_meta.get("purpose")
                or "—"
            )
            docs = (
                svc_x_docs.get("docs")
                or file_x_docs.get("docs")
                or svc_meta.get("docs")
                or f"[compose]({rel_path})"
            )
            node = str(
                svc_x_docs.get("node")
                or file_x_docs.get("node")
                or svc_meta.get("node")
                or default_node
            )

            services.append(
                ServiceEntry(
                    name=svc_name,
                    node=node,
                    container_name=str(svc_cfg.get("container_name", svc_name)),
                    image=str(svc_cfg.get("image", "local build")),
                    networks=normalize_networks(svc_cfg),
                    ports=normalize_ports(svc_cfg),
                    restart=str(svc_cfg.get("restart", "no")),
                    purpose=purpose,
                    docs=docs,
                    source=rel_path,
                )
            )

    return sorted(services, key=lambda s: (s.node.lower(), s.name.lower()))


def merge_services(
    snapshots: list[NodeSnapshot],
    compose_services: list[ServiceEntry],
) -> list[ServiceEntry]:
    """Use live container data from node snapshots when available; fill remaining from compose files."""
    per_node_agents = {"node-exporter"}
    live_nodes = {snap.node for snap in snapshots if snap.containers}
    live_services = {c.name for snap in snapshots for c in snap.containers}
    compose_by_name = {s.name: s for s in compose_services}
    merged: list[ServiceEntry] = []

    for snap in snapshots:
        for c in snap.containers:
            # Enrich live container with compose doc link if available
            if c.docs == "—" and c.name in compose_by_name:
                c.docs = compose_by_name[c.name].docs
            merged.append(c)

    # Keep static compose services for nodes that haven't pushed live container snapshots yet,
    # skipping services already discovered live on another node (except per-node agents).
    for s in compose_services:
        if s.node in live_nodes:
            continue
        if s.name in live_services and s.name not in per_node_agents:
            continue
        merged.append(s)

    return sorted(merged, key=lambda s: (s.node.lower(), s.name.lower()))


def parse_nginx_routes() -> list[NginxRoute]:
    if not NGINX_CONF.exists():
        return []

    text = NGINX_CONF.read_text(encoding="utf-8")
    routes: list[NginxRoute] = []

    idx = 0
    while True:
        m = re.search(r"\bserver\s*\{", text[idx:])
        if not m:
            break
        start = idx + m.end()
        depth = 1
        pos = start
        while pos < len(text) and depth > 0:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
            pos += 1
        block = text[start : pos - 1]
        idx = pos

        proxy_match = re.search(r"proxy_pass\s+https?://([^:/;\s]+)(?::(\d+))?", block)
        if not proxy_match:
            continue

        server_match = re.search(r"server_name\s+([^;]+);", block)
        server_name = server_match.group(1).strip() if server_match else "unknown"
        ssl = bool(re.search(r"listen\s+443\s+ssl", block))
        websocket = "proxy-websocket" in block or "Upgrade" in block

        routes.append(
            NginxRoute(
                server_name=server_name,
                upstream_host=proxy_match.group(1),
                upstream_port=proxy_match.group(2) or "80",
                ssl=ssl,
                websocket=websocket,
            )
        )

    return routes


def parse_prometheus() -> tuple[str, list[PrometheusJob]]:
    if not PROMETHEUS_CONF.exists():
        return "unknown", []

    data = yaml.safe_load(PROMETHEUS_CONF.read_text(encoding="utf-8")) or {}
    interval = str((data.get("global") or {}).get("scrape_interval", "default"))
    jobs: list[PrometheusJob] = []

    for cfg in data.get("scrape_configs") or []:
        job_name = str(cfg.get("job_name", "unnamed"))
        targets: list[str] = []
        for sc in cfg.get("static_configs") or []:
            targets.extend(str(t) for t in (sc.get("targets") or []))
        jobs.append(PrometheusJob(job_name=job_name, targets=targets))

    return interval, jobs


def mermaid_id(prefix: str, raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", f"{prefix}_{raw}")


def build_mermaid_topology(
    snapshots: list[NodeSnapshot],
    services: list[ServiceEntry],
    nginx_routes: list[NginxRoute],
    prom_jobs: list[PrometheusJob],
    meta: dict[str, Any],
) -> str:
    lines: list[str] = ["```mermaid", "flowchart LR"]
    meta_nodes: dict[str, dict[str, str]] = meta.get("nodes") or {}
    snap_by_node = {s.node: s for s in snapshots}

    # Group services by node
    node_keys = sorted(
        set(snap_by_node.keys())
        | {s.node for s in services}
        | set(meta_nodes.keys())
    )

    host_to_id: dict[str, str] = {}
    node_host_to_id: dict[tuple[str, str], str] = {}
    service_node: dict[str, str] = {}

    for node_key in node_keys:
        node_services = [s for s in services if s.node == node_key]
        snap = snap_by_node.get(node_key)
        display = (
            snap.display_name
            if snap
            else (meta_nodes.get(node_key, {}).get("display_name") or node_key)
        )
        os_suffix = f" — {snap.os}" if snap else " (Debian)"
        sg_id = mermaid_id("node", node_key)
        lines.append(f'  subgraph {sg_id}["{display}{os_suffix}"]')

        node_nets = sorted({n for s in node_services for n in s.networks})
        for net in node_nets:
            nid = mermaid_id(f"net_{node_key}", net)
            lines.append(f'    {nid}{{{{"{net}"}}}}')

        for s in node_services:
            sid = mermaid_id(f"svc_{node_key}", s.name)
            host_to_id.setdefault(s.name, sid)
            host_to_id.setdefault(s.container_name, sid)
            node_host_to_id[(node_key, s.name)] = sid
            node_host_to_id[(node_key, s.container_name)] = sid
            service_node.setdefault(s.name, node_key)
            label = s.name if s.container_name == s.name else f"{s.name} ({s.container_name})"
            lines.append(f'    {sid}["{label}"]')
            for net in s.networks:
                lines.append(f"    {sid} --- {mermaid_id(f'net_{node_key}', net)}")

        if snap:
            for idx, hs in enumerate(snap.host_services):
                if hs == "Docker" and node_services:
                    continue
                lines.append(f'    {mermaid_id(f"hs_{node_key}", str(idx))}["host: {hs}"]')
            for idx, t in enumerate(snap.timers):
                lines.append(
                    f'    {mermaid_id(f"tm_{node_key}", str(idx))}["timer: {t.name} ({t.schedule})"]'
                )
        elif not node_services:
            role = meta_nodes.get(node_key, {}).get("role") or "Pending snapshot"
            lines.append(f'    {mermaid_id("info", node_key)}["{role}"]')

        lines.append("  end")

    def resolve_target(source_node: str | None, host: str) -> str | None:
        if source_node and (source_node, host) in node_host_to_id:
            return node_host_to_id[(source_node, host)]
        return host_to_id.get(host)

    # NGINX reverse proxy edges
    nginx_id = host_to_id.get("nginx")
    nginx_node = service_node.get("nginx")
    if nginx_id and nginx_routes:
        for route in nginx_routes:
            target_id = resolve_target(nginx_node, route.upstream_host)
            if target_id:
                host_label = route.server_name.replace("${Domain}", "domain")
                lines.append(f'  {nginx_id} -. "HTTPS {host_label}" .-> {target_id}')

    # Prometheus scrape edges
    prom_id = host_to_id.get("prometheus")
    prom_node = service_node.get("prometheus")
    if prom_id and prom_jobs:
        for job in prom_jobs:
            for target in job.targets:
                host = target.split(":")[0]
                if host in ("localhost", "127.0.0.1"):
                    continue
                target_id = resolve_target(prom_node, host)
                if target_id:
                    lines.append(f'  {prom_id} -. "scrape" .-> {target_id}')

    lines.append("```")
    return "\n".join(lines)


def build_nodes_table(snapshots: list[NodeSnapshot], meta: dict[str, Any]) -> str:
    meta_nodes: dict[str, dict[str, str]] = meta.get("nodes") or {}
    snap_by_node = {s.node: s for s in snapshots}
    all_nodes = sorted(set(snap_by_node.keys()) | set(meta_nodes.keys()))

    rows = [
        "| Node | Role | OS / Arch | Hardware | Host Services |",
        "| ---- | ---- | --------- | -------- | ------------- |",
    ]

    for key in all_nodes:
        snap = snap_by_node.get(key)
        if snap:
            hw = f"{snap.cpu_cores}c · {snap.ram_gb} GB RAM · {snap.root_disk_gb} GB disk"
            os_arch = f"`{snap.os}` (`{snap.arch}`)"
            host_svcs = ", ".join(f"`{h}`" for h in snap.host_services) or "—"
            rows.append(
                f"| **{snap.display_name}** (`{snap.node}`) | {snap.role} | {os_arch} | {hw} | {host_svcs} |"
            )
        else:
            info = meta_nodes[key]
            rows.append(
                f"| **{info.get('display_name', key)}** (`{key}`) | {info.get('role', '—')} | `Debian` *(pending sync)* | — | — |"
            )

    return "\n".join(rows)


def build_readme_services_table(
    services: list[ServiceEntry],
    meta: dict[str, Any],
) -> str:
    rows = [
        "| Node | Service | Image / Stack | Networks | Purpose | Docs |",
        "| ---- | ------- | ------------- | -------- | ------- | ---- |",
    ]
    for s in services:
        nets = ", ".join(f"`{n}`" for n in s.networks)
        rows.append(
            f"| `{s.node}` | `{s.name}` | `{s.image}` | {nets} | {s.purpose} | {s.docs} |"
        )

    existing_names = {s.name for s in services}
    for w in meta.get("host_workloads") or []:
        if w["name"] in existing_names:
            continue
        rows.append(
            f"| `{w.get('node', 'host')}` | `{w['name']}` | `{w['stack']}` | `host` | {w['purpose']} | {w['docs']} |"
        )

    rows.append("")
    rows.append(
        "> *Auto-generated from `nodes/*.json` and `docker-compose/*/compose.yaml` via `scripts/generate_docs.py`. "
        "See [`docs/inventory.md`](docs/inventory.md) for full hardware specs, ports, NGINX routes, Prometheus targets, and systemd timers.*"
    )
    return "\n".join(rows)


def build_readme_topology_block(mermaid_block: str) -> str:
    return "\n".join(
        [
            "<details>",
            "<summary><strong>Auto-generated Multi-Node Topology Diagram (Mermaid)</strong></summary>",
            "",
            mermaid_block,
            "",
            "</details>",
        ]
    )


def build_inventory_md(
    snapshots: list[NodeSnapshot],
    services: list[ServiceEntry],
    nginx_routes: list[NginxRoute],
    prom_interval: str,
    prom_jobs: list[PrometheusJob],
    mermaid_block: str,
    meta: dict[str, Any],
) -> str:
    networks = sorted({n for s in services for n in s.networks})
    all_timers = [t for snap in snapshots for t in snap.timers]
    node_count = len(set(s.node for s in snapshots) | set((meta.get("nodes") or {}).keys()))

    sections: list[str] = [
        "# Home Lab — Auto-Generated Inventory",
        "",
        "> **Do not edit manually.** Generated by `scripts/generate_docs.py` from `nodes/*.json`, `docker-compose/`, and `scripts/metadata.yaml`.",
        "",
        "## Overview",
        "",
        "| Metric | Count |",
        "| ------ | ----- |",
        f"| Physical Nodes | {node_count} ({len(snapshots)} synced live) |",
        f"| Docker Services | {len(services)} |",
        f"| Docker Networks | {len(networks)} ({', '.join(f'`{n}`' for n in networks)}) |",
        f"| NGINX Reverse Proxy Routes | {len(nginx_routes)} |",
        f"| Prometheus Scrape Jobs | {len(prom_jobs)} (`{prom_interval}` interval) |",
        f"| Custom Systemd Timers | {len(all_timers)} |",
        "",
        "## Nodes & Hardware",
        "",
        build_nodes_table(snapshots, meta),
        "",
        "## Network & Service Topology",
        "",
        mermaid_block,
        "",
        "## Docker Services",
        "",
        "| Node | Service | Container | Image | Networks | Exposed Ports | Restart | Source |",
        "| ---- | ------- | --------- | ----- | -------- | ------------- | ------- | ------ |",
    ]

    for s in services:
        nets = ", ".join(f"`{n}`" for n in s.networks)
        ports = ", ".join(f"`{p}`" for p in s.ports) if s.ports else "—"
        src = (
            f"live (`{s.status}`)"
            if s.source == "live"
            else f"[compose](../{s.source})"
        )
        sections.append(
            f"| `{s.node}` | `{s.name}` | `{s.container_name}` | `{s.image}` | {nets} | {ports} | `{s.restart}` | {src} |"
        )

    sections.extend(
        [
            "",
            "## NGINX Reverse Proxy Routes",
            "",
            "| Virtual Host | Upstream Target | TLS (443) | WebSocket |",
            "| ------------ | --------------- | --------- | --------- |",
        ]
    )
    for r in nginx_routes:
        tls = "Yes" if r.ssl else "No"
        ws = "Yes" if r.websocket else "No"
        sections.append(
            f"| `{r.server_name}` | `http://{r.upstream_host}:{r.upstream_port}` | {tls} | {ws} |"
        )

    sections.extend(
        [
            "",
            f"## Prometheus Scrape Targets (`scrape_interval: {prom_interval}`)",
            "",
            "| Job | Targets |",
            "| --- | ------- |",
        ]
    )
    for j in prom_jobs:
        targets = ", ".join(f"`{t}`" for t in j.targets)
        sections.append(f"| `{j.job_name}` | {targets} |")

    if all_timers:
        sections.extend(
            [
                "",
                "## Custom Systemd Timers",
                "",
                "| Node | Timer | Schedule | Enabled | Description |",
                "| ---- | ----- | -------- | ------- | ----------- |",
            ]
        )
        for t in all_timers:
            sections.append(
                f"| `{t.node}` | `{t.name}` | `{t.schedule}` | `{t.enabled}` | {t.description} |"
            )

    sections.append("")
    return "\n".join(sections)


def replace_marker_block(text: str, marker: str, replacement: str) -> str:
    start_tag = f"<!-- AUTO:{marker}:START -->"
    end_tag = f"<!-- AUTO:{marker}:END -->"
    pattern = re.compile(
        rf"({re.escape(start_tag)})(.*?)({re.escape(end_tag)})",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise ValueError(f"Marker pair {start_tag} / {end_tag} not found in README.md")
    return pattern.sub(rf"\1\n{replacement}\n\3", text, count=1)


def print_config_warnings(services: list[ServiceEntry]) -> None:
    for s in services:
        if s.restart == "no":
            print(f"[warn] {s.node}/{s.name}: no restart policy set", file=sys.stderr)
        if s.image.endswith(":latest") or ":" not in s.image:
            print(f"[info] {s.node}/{s.name}: unpinned image tag ({s.image})", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-generate Home Lab documentation.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated docs are up to date without modifying files.",
    )
    args = parser.parse_args()

    meta = load_metadata()
    snapshots = parse_node_snapshots(meta)
    compose_services = parse_compose_services(meta)
    services = merge_services(snapshots, compose_services)
    nginx_routes = parse_nginx_routes()
    prom_interval, prom_jobs = parse_prometheus()

    mermaid_block = build_mermaid_topology(snapshots, services, nginx_routes, prom_jobs, meta)
    inventory_content = build_inventory_md(
        snapshots, services, nginx_routes, prom_interval, prom_jobs, mermaid_block, meta
    )

    readme_original = README_FILE.read_text(encoding="utf-8")
    readme_updated = replace_marker_block(
        readme_original,
        "NODES",
        build_nodes_table(snapshots, meta),
    )
    readme_updated = replace_marker_block(
        readme_updated,
        "SERVICES",
        build_readme_services_table(services, meta),
    )
    readme_updated = replace_marker_block(
        readme_updated,
        "TOPOLOGY",
        build_readme_topology_block(mermaid_block),
    )

    print_config_warnings(services)

    inventory_original = INVENTORY_FILE.read_text(encoding="utf-8") if INVENTORY_FILE.exists() else ""
    stale_files: list[str] = []
    if inventory_content != inventory_original:
        stale_files.append(INVENTORY_FILE.relative_to(REPO_ROOT).as_posix())
    if readme_updated != readme_original:
        stale_files.append(README_FILE.relative_to(REPO_ROOT).as_posix())

    if args.check:
        if stale_files:
            print(
                f"Documentation is out of date ({', '.join(stale_files)}). "
                "Run `python3 scripts/generate_docs.py`.",
                file=sys.stderr,
            )
            return 1
        print("Documentation is up to date.")
        return 0

    INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_FILE.write_text(inventory_content, encoding="utf-8")
    README_FILE.write_text(readme_updated, encoding="utf-8")

    print(
        f"Updated docs: {len(snapshots)} live node snapshot(s), "
        f"{len(services)} Docker services, "
        f"{len(nginx_routes)} NGINX routes, "
        f"{len(prom_jobs)} Prometheus jobs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
