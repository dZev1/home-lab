#!/usr/bin/env python3
"""Collect sanitized hardware, OS, Docker, and systemd metadata from the current Linux node.

Zero external dependencies (Python 3.10+ stdlib only) so it can run on any Debian/Linux node.

Security / privacy guarantees for public repositories:
  - NEVER reads container environment variables (no secrets/passwords/tokens)
  - NEVER exports IP addresses, MAC addresses, usernames, or private host mount paths
  - ONLY reads custom systemd timers under /etc/systemd/system/ (ignores OS noise)

Usage:
  python3 scripts/collect_node.py --dry-run
  python3 scripts/collect_node.py --role "Media Server"
  python3 scripts/collect_node.py --node-name mac-mini --role "Media Server"
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
NODES_DIR = REPO_ROOT / "nodes"

# Allowlist of well-known infrastructure host services to check via systemctl
HOST_SERVICE_ALLOWLIST = [
    ("ssh", "OpenSSH"),
    ("sshd", "OpenSSH"),
    ("tailscaled", "Tailscale"),
    ("docker", "Docker"),
    ("nginx", "NGINX"),
    ("ufw", "UFW Firewall"),
    ("fail2ban", "Fail2Ban"),
    ("prometheus-node-exporter", "Node Exporter"),
    ("forgejo", "Forgejo"),
    ("jellyfin", "Jellyfin"),
]


def run_cmd(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 1, ""


def get_os_pretty_name() -> str:
    os_release = Path("/etc/os-release")
    if os_release.exists():
        for line in os_release.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return f"{platform.system()} {platform.release()}"


def get_cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        text = cpuinfo.read_text(encoding="utf-8", errors="ignore")
        for key in ("Model", "model name", "Hardware"):
            m = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", text, re.MULTILINE)
            if m:
                return re.sub(r"\s+", " ", m.group(1).strip())
    return platform.processor() or platform.machine()


def get_ram_gb() -> float:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        m = re.search(r"^MemTotal:\s+(\d+)\s+kB", meminfo.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            return round(int(m.group(1)) / (1024 * 1024), 1)
    return 0.0


def get_root_disk_gb() -> float:
    try:
        usage = shutil.disk_usage("/")
        return round(usage.total / (1024**3), 1)
    except OSError:
        return 0.0


def get_active_host_services() -> list[str]:
    if not shutil.which("systemctl"):
        return []
    active: list[str] = []
    seen_labels: set[str] = set()
    for unit, label in HOST_SERVICE_ALLOWLIST:
        if label in seen_labels:
            continue
        rc, out = run_cmd(["systemctl", "is-active", unit])
        if rc == 0 and out == "active":
            active.append(label)
            seen_labels.add(label)

    # Also check active WireGuard interfaces without leaking interface names
    rc, out = run_cmd(["systemctl", "list-units", "--type=service", "--state=active", "wg-quick@*", "--no-legend"])
    if rc == 0 and out:
        active.append("WireGuard")

    return sorted(active)


def get_custom_systemd_timers() -> list[dict[str, str]]:
    """Read custom .timer files under /etc/systemd/system/ (excludes default OS timers)."""
    systemd_dir = Path("/etc/systemd/system")
    if not systemd_dir.exists():
        return []

    timers: list[dict[str, str]] = []
    for timer_file in sorted(systemd_dir.glob("*.timer")):
        if timer_file.is_symlink() and str(timer_file.resolve()) == "/dev/null":
            continue
        content = timer_file.read_text(encoding="utf-8", errors="ignore")
        name = timer_file.stem

        schedule = "custom"
        if m := re.search(r"^OnCalendar=(.+)$", content, re.MULTILINE):
            schedule = m.group(1).strip()
        elif m := re.search(r"^OnUnitActiveSec=(.+)$", content, re.MULTILINE):
            schedule = f"every {m.group(1).strip()}"

        description = "—"
        if m := re.search(r"^Description=(.+)$", content, re.MULTILINE):
            description = m.group(1).strip()
        else:
            svc_file = systemd_dir / f"{name}.service"
            if svc_file.exists():
                svc_text = svc_file.read_text(encoding="utf-8", errors="ignore")
                if m := re.search(r"^Description=(.+)$", svc_text, re.MULTILINE):
                    description = m.group(1).strip()

        enabled = "unknown"
        if shutil.which("systemctl"):
            rc, out = run_cmd(["systemctl", "is-enabled", timer_file.name])
            enabled = out if rc == 0 else "disabled"

        timers.append(
            {
                "name": name,
                "schedule": schedule,
                "description": description,
                "enabled": enabled,
            }
        )

    return timers


def sanitize_ports(port_bindings: dict[str, Any] | None) -> list[str]:
    """Extract sanitized port mappings (host_port:container_port/proto), stripping IPs."""
    if not port_bindings:
        return []
    ports: set[str] = set()
    for container_port, bindings in port_bindings.items():
        if not bindings:
            continue
        for b in bindings:
            host_port = (b or {}).get("HostPort", "")
            if host_port:
                ports.add(f"{host_port}:{container_port}")
    return sorted(ports)


def get_docker_containers(
    exclude_projects: set[str],
    exclude_services: set[str],
    include_stopped: bool = False,
) -> list[dict[str, Any]]:
    if not shutil.which("docker"):
        return []

    ps_cmd = ["docker", "ps", "-aq"] if include_stopped else ["docker", "ps", "-q"]
    rc, ids_out = run_cmd(ps_cmd)
    if rc != 0 or not ids_out:
        return []

    container_ids = [cid for cid in ids_out.splitlines() if cid.strip()]
    if not container_ids:
        return []

    rc, inspect_out = run_cmd(["docker", "inspect", *container_ids], timeout=20)
    if rc != 0 or not inspect_out:
        return []

    try:
        raw_items = json.loads(inspect_out)
    except json.JSONDecodeError:
        return []

    generic_names = {"server", "app", "web", "service", "main"}
    containers: list[dict[str, Any]] = []
    for item in raw_items:
        cfg = item.get("Config") or {}
        host_cfg = item.get("HostConfig") or {}
        net_settings = item.get("NetworkSettings") or {}
        state = item.get("State") or {}
        labels = cfg.get("Labels") or {}

        if str(labels.get("homelab.hide", "")).lower() in ("1", "true", "yes"):
            continue

        name = str(item.get("Name", "")).lstrip("/")
        raw_service = str(labels.get("com.docker.compose.service") or name)
        compose_service = name if raw_service.lower() in generic_names and name else raw_service
        compose_project = str(labels.get("com.docker.compose.project") or "")

        if compose_project.lower() in exclude_projects:
            continue
        if compose_service.lower() in exclude_services or name.lower() in exclude_services:
            continue

        image = str(cfg.get("Image", "unknown"))

        networks = sorted((net_settings.get("Networks") or {}).keys())
        if not networks:
            net_mode = str(host_cfg.get("NetworkMode", "default"))
            networks = [net_mode]

        restart_policy = str((host_cfg.get("RestartPolicy") or {}).get("Name", "no")) or "no"
        ports = sanitize_ports(host_cfg.get("PortBindings"))

        entry: dict[str, Any] = {
            "service": compose_service,
            "container_name": name,
            "project": compose_project,
            "image": image,
            "status": str(state.get("Status", "unknown")),
            "networks": networks,
            "ports": ports,
            "restart": restart_policy,
        }

        # Optional documentation labels (homelab.purpose / homelab.docs)
        if labels.get("homelab.purpose"):
            entry["purpose"] = str(labels["homelab.purpose"])
        if labels.get("homelab.docs"):
            entry["docs"] = str(labels["homelab.docs"])

        containers.append(entry)

    return sorted(containers, key=lambda c: (c["service"].lower(), c["container_name"].lower()))


def parse_csv_set(values: list[str] | None) -> set[str]:
    result: set[str] = set()
    for val in values or []:
        for item in val.split(","):
            cleaned = item.strip().lower()
            if cleaned:
                result.add(cleaned)
    return result


def collect_snapshot(
    node_name: str,
    role: str,
    exclude_projects: set[str],
    exclude_services: set[str],
    include_stopped: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "node": node_name,
        "role": role,
        "system": {
            "os": get_os_pretty_name(),
            "kernel": platform.release(),
            "arch": platform.machine(),
            "cpu": get_cpu_model(),
            "cpu_cores": os.cpu_count() or 0,
            "ram_gb": get_ram_gb(),
            "root_disk_gb": get_root_disk_gb(),
        },
        "host_services": get_active_host_services(),
        "systemd_timers": get_custom_systemd_timers(),
        "docker_containers": get_docker_containers(
            exclude_projects, exclude_services, include_stopped=include_stopped
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect sanitized node snapshot for Home Lab docs.")
    parser.add_argument(
        "--node-name",
        default=socket.gethostname(),
        help="Logical node name used for nodes/<name>.json (defaults to hostname).",
    )
    parser.add_argument(
        "--role",
        default="",
        help="Short description of this node's role (e.g., 'Media Server', 'Core Services').",
    )
    parser.add_argument(
        "--exclude-project",
        action="append",
        default=[],
        help="Docker Compose project name(s) to exclude (repeatable or comma-separated).",
    )
    parser.add_argument(
        "--exclude-service",
        action="append",
        default=[],
        help="Service or container name(s) to exclude (repeatable or comma-separated).",
    )
    parser.add_argument(
        "--include-stopped",
        action="store_true",
        help="Include exited/stopped containers (by default only running containers are collected).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print collected JSON to stdout without writing any file.",
    )
    args = parser.parse_args()

    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", args.node_name.strip().lower())
    exclude_projects = parse_csv_set(args.exclude_project)
    exclude_services = parse_csv_set(args.exclude_service)
    snapshot = collect_snapshot(
        safe_name,
        args.role.strip(),
        exclude_projects,
        exclude_services,
        include_stopped=args.include_stopped,
    )
    rendered = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"

    if args.dry_run:
        print(rendered, end="")
        return 0

    NODES_DIR.mkdir(parents=True, exist_ok=True)
    out_file = NODES_DIR / f"{safe_name}.json"
    out_file.write_text(rendered, encoding="utf-8")
    print(
        f"Saved {out_file.relative_to(REPO_ROOT)} "
        f"({len(snapshot['docker_containers'])} containers, "
        f"{len(snapshot['systemd_timers'])} custom timers)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
