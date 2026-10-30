#!/usr/bin/env python3
"""homelab-status: a small, read-only JSON status endpoint for this host.

Hermes runs inside a K3s container and can't see the host's disks, Docker,
GPU or services, so this runs on the host itself and Hermes' System page
reads it (GET /status). Python standard library only — nothing to install.

Read-only by design: it only ever lists and measures, never starts, stops or
changes anything. It has no login, so it is meant for the LAN/tailnet only
(never port-forward it).

K3s pods/cronjobs need root to read the cluster config; those two commands
are run through a sudoers rule that allows exactly them (see
homelab-status.service for the one-time setup). Until that rule exists the
"k3s" section reports an error and everything else still works.
"""

import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("STATUS_PORT", "8190"))
STORAGE_ROOT = os.environ.get("STORAGE_ROOT", "/mnt/storage")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/mnt/storage/planner-backups")
K3S = os.environ.get("K3S_BIN", "/usr/local/bin/k3s")
SYSTEMD_UNITS = [
    "ollama", "iris", "codebase-searcher", "vault-keeper", "images-after-dark",
    "k3s", "docker", "smbd", "tailscaled", "cron",
]
CACHE_SECONDS = 5
DU_REFRESH_SECONDS = 600
REAL_FSTYPES = {"ext4", "xfs", "btrfs", "zfs", "f2fs", "ext3"}


def run(cmd: list[str], timeout: float = 10.0) -> tuple[bool, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if out.returncode != 0:
        return False, (out.stderr or out.stdout).strip()
    return True, out.stdout


# ---- host -----------------------------------------------------------------

_cpu_percent = 0.0


def _read_cpu_times() -> tuple[int, int]:
    with open("/proc/stat") as f:
        fields = [int(x) for x in f.readline().split()[1:]]
    idle = fields[3] + fields[4]  # idle + iowait
    return idle, sum(fields)


def _cpu_sampler() -> None:
    global _cpu_percent
    prev_idle, prev_total = _read_cpu_times()
    while True:
        time.sleep(2)
        idle, total = _read_cpu_times()
        d_total = total - prev_total
        if d_total > 0:
            _cpu_percent = round(100.0 * (1 - (idle - prev_idle) / d_total), 1)
        prev_idle, prev_total = idle, total


def _meminfo() -> dict:
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0]) * 1024
    return {
        "total": info.get("MemTotal", 0),
        "available": info.get("MemAvailable", 0),
        "swap_total": info.get("SwapTotal", 0),
        "swap_free": info.get("SwapFree", 0),
    }


def _temperatures() -> list[dict]:
    temps = []
    base = "/sys/class/hwmon"
    try:
        chips = sorted(os.listdir(base))
    except OSError:
        return temps
    for chip in chips:
        try:
            name = open(f"{base}/{chip}/name").read().strip()
        except OSError:
            continue
        for entry in sorted(os.listdir(f"{base}/{chip}")):
            m = re.fullmatch(r"temp(\d+)_input", entry)
            if not m:
                continue
            try:
                value = int(open(f"{base}/{chip}/{entry}").read().strip()) / 1000
                label_path = f"{base}/{chip}/temp{m.group(1)}_label"
                label = open(label_path).read().strip() if os.path.exists(label_path) else f"temp{m.group(1)}"
            except (OSError, ValueError):
                continue
            temps.append({"chip": name, "label": label, "c": round(value, 1)})
    return temps


def host_info() -> dict:
    try:
        pretty = next(
            (l.split("=", 1)[1].strip().strip('"') for l in open("/etc/os-release") if l.startswith("PRETTY_NAME=")), ""
        )
    except OSError:
        pretty = ""
    uptime = float(open("/proc/uptime").read().split()[0])
    return {
        "hostname": os.uname().nodename,
        "os": pretty,
        "kernel": os.uname().release,
        "uptime_seconds": int(uptime),
        "load": [round(x, 2) for x in os.getloadavg()],
        "cpu_count": os.cpu_count(),
        "cpu_percent": _cpu_percent,
        "memory": _meminfo(),
        "temperatures": _temperatures(),
        "reboot_required": os.path.exists("/var/run/reboot-required"),
    }


# ---- storage --------------------------------------------------------------


def disks() -> list[dict]:
    seen, out = set(), []
    with open("/proc/mounts") as f:
        for line in f:
            device, mount, fstype = line.split()[:3]
            if fstype not in REAL_FSTYPES or device in seen:
                continue
            seen.add(device)
            try:
                st = os.statvfs(mount)
            except OSError:
                continue
            total = st.f_blocks * st.f_frsize
            avail = st.f_bavail * st.f_frsize
            used = total - st.f_bfree * st.f_frsize
            if total <= 0:
                continue
            out.append({"mount": mount, "device": device, "fstype": fstype, "total": total, "used": used, "available": avail})
    out.sort(key=lambda d: d["mount"])
    return out


_du_cache: dict = {"entries": [], "updated_at": None, "partial": []}
_du_lock = threading.Lock()


def _refresh_du() -> None:
    # Per-folder sizes under the storage root. Folders this user can't read
    # (root-owned) come back undercounted, so they're flagged as partial
    # rather than shown as if the number were complete.
    try:
        proc = subprocess.run(
            ["du", "-k", "-x", "--max-depth=1", STORAGE_ROOT], capture_output=True, text=True, timeout=300
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    partial = set()
    for line in proc.stderr.splitlines():
        m = re.search(r"'([^']+)'", line)
        if m and "Permission denied" in line:
            top = m.group(1)[len(STORAGE_ROOT):].strip("/").split("/")[0]
            if top:
                partial.add(top)
    entries = []
    for line in proc.stdout.splitlines():
        kb, _, path = line.partition("\t")
        if not kb.isdigit() or path.rstrip("/") == STORAGE_ROOT.rstrip("/"):
            continue
        entries.append({"name": os.path.basename(path), "bytes": int(kb) * 1024})
    entries.sort(key=lambda e: e["bytes"], reverse=True)
    with _du_lock:
        _du_cache.update(entries=entries, updated_at=int(time.time()), partial=sorted(partial))


def _du_loop() -> None:
    while True:
        _refresh_du()
        time.sleep(DU_REFRESH_SECONDS)


def storage_breakdown() -> dict:
    with _du_lock:
        return {"root": STORAGE_ROOT, **_du_cache}


def backups() -> dict:
    try:
        files = [
            (os.path.getmtime(os.path.join(BACKUP_DIR, n)), n, os.path.getsize(os.path.join(BACKUP_DIR, n)))
            for n in os.listdir(BACKUP_DIR)
            if os.path.isfile(os.path.join(BACKUP_DIR, n))
        ]
    except OSError as exc:
        return {"error": str(exc)}
    if not files:
        return {"dir": BACKUP_DIR, "count": 0, "latest": None}
    mtime, name, size = max(files)
    return {
        "dir": BACKUP_DIR,
        "count": len(files),
        "latest": {"name": name, "bytes": size, "age_seconds": int(time.time() - mtime)},
    }


# ---- gpu ------------------------------------------------------------------


def gpu() -> dict:
    ok, out = run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.used,memory.total,temperature.gpu,utilization.gpu,power.draw",
         "--format=csv,noheader,nounits"]
    )
    if not ok:
        return {"error": out.splitlines()[0] if out else "nvidia-smi failed"}
    name, driver, mem_used, mem_total, temp, util, power = [x.strip() for x in out.splitlines()[0].split(",")]

    def num(x):
        try:
            return float(x)
        except ValueError:
            return None

    return {
        "name": name,
        "driver": driver,
        "memory_used": int(num(mem_used) * 1024 * 1024) if num(mem_used) is not None else None,
        "memory_total": int(num(mem_total) * 1024 * 1024) if num(mem_total) is not None else None,
        "temperature_c": num(temp),
        "utilization_percent": num(util),
        "power_watts": num(power),
    }


# ---- docker / systemd -----------------------------------------------------


def docker() -> dict:
    ok, out = run(["docker", "ps", "-a", "--format", "{{json .}}"])
    if not ok:
        return {"error": out.splitlines()[0] if out else "docker failed"}
    containers = []
    for line in out.splitlines():
        try:
            c = json.loads(line)
        except ValueError:
            continue
        status = c.get("Status", "")
        containers.append(
            {
                "name": c.get("Names", ""),
                "image": c.get("Image", ""),
                "state": c.get("State", ""),
                "status": status,
                "healthy": "(healthy)" in status,
                "unhealthy": "(unhealthy)" in status,
                "ports": c.get("Ports", ""),
            }
        )
    containers.sort(key=lambda c: c["name"])
    return {"containers": containers}


def systemd_units() -> list[dict]:
    ok, out = run(
        ["systemctl", "show", *[f"{u}.service" for u in SYSTEMD_UNITS],
         "-p", "Id,ActiveState,SubState,ActiveEnterTimestampMonotonic,NRestarts"]
    )
    if not ok:
        return [{"name": u, "state": "unknown"} for u in SYSTEMD_UNITS]
    uptime = float(open("/proc/uptime").read().split()[0])
    units = []
    for block in out.strip().split("\n\n"):
        props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        mono = int(props.get("ActiveEnterTimestampMonotonic", "0") or 0)
        active = props.get("ActiveState", "unknown")
        units.append(
            {
                "name": props.get("Id", "").removesuffix(".service"),
                "state": active,
                "sub": props.get("SubState", ""),
                "since_seconds": int(uptime - mono / 1e6) if active == "active" and mono else None,
                "restarts": int(props.get("NRestarts", "0") or 0),
            }
        )
    return units


# ---- k3s ------------------------------------------------------------------


def _age_seconds(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - then).total_seconds()))


def summarize_pods(data: dict) -> list[dict]:
    pods = []
    for item in data.get("items", []):
        meta, status, spec = item.get("metadata", {}), item.get("status", {}), item.get("spec", {})
        containers = status.get("containerStatuses") or []
        total = len(spec.get("containers", [])) or len(containers)
        ready = sum(1 for c in containers if c.get("ready"))
        restarts = sum(c.get("restartCount", 0) for c in containers)
        phase = status.get("phase", "Unknown")
        # A pod can be "Pending"/"Running" yet stuck: surface the container's
        # own reason (ErrImageNeverPull, CrashLoopBackOff, ...) when there is one.
        reason = ""
        for c in containers:
            waiting = (c.get("state") or {}).get("waiting") or {}
            terminated = (c.get("state") or {}).get("terminated") or {}
            reason = waiting.get("reason") or (terminated.get("reason") if phase == "Failed" else "") or reason
        if not reason and phase == "Pending":
            for cond in status.get("conditions", []):
                if cond.get("status") == "False" and cond.get("reason"):
                    reason = cond["reason"]
        ok = phase == "Succeeded" or (phase == "Running" and total > 0 and ready == total)
        pods.append(
            {
                "namespace": meta.get("namespace", ""),
                "name": meta.get("name", ""),
                "phase": phase,
                "ready": f"{ready}/{total}",
                "restarts": restarts,
                "reason": reason,
                "ok": ok,
                "age_seconds": _age_seconds(meta.get("creationTimestamp")),
            }
        )
    pods.sort(key=lambda p: (p["namespace"], p["name"]))
    return pods


def summarize_cronjobs(data: dict) -> list[dict]:
    jobs = []
    for item in data.get("items", []):
        meta, spec, status = item.get("metadata", {}), item.get("spec", {}), item.get("status", {})
        jobs.append(
            {
                "namespace": meta.get("namespace", ""),
                "name": meta.get("name", ""),
                "schedule": spec.get("schedule", ""),
                "suspended": bool(spec.get("suspend")),
                "active": len(status.get("active") or []),
                "last_schedule_age_seconds": _age_seconds(status.get("lastScheduleTime")),
                "last_success_age_seconds": _age_seconds(status.get("lastSuccessfulTime")),
            }
        )
    jobs.sort(key=lambda j: (j["namespace"], j["name"]))
    return jobs


def k3s() -> dict:
    ok, out = run(["sudo", "-n", K3S, "kubectl", "get", "pods", "-A", "-o", "json"], timeout=15)
    if not ok:
        first = out.splitlines()[0] if out else "kubectl failed"
        if any(t in out for t in ("password is required", "a terminal is required", "interactive authentication", "not allowed")):
            first = "not set up yet: the one-time sudoers rule for kubectl is missing"
        return {"error": first}
    try:
        pods = summarize_pods(json.loads(out))
    except ValueError:
        return {"error": "couldn't read kubectl output"}
    ok, out = run(["sudo", "-n", K3S, "kubectl", "get", "cronjobs", "-A", "-o", "json"], timeout=15)
    cronjobs = []
    if ok:
        try:
            cronjobs = summarize_cronjobs(json.loads(out))
        except ValueError:
            pass
    return {"pods": pods, "cronjobs": cronjobs}


# ---- assemble -------------------------------------------------------------

_cache: dict = {"at": 0.0, "data": None}
_cache_lock = threading.Lock()


def collect() -> dict:
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            "host": pool.submit(host_info),
            "disks": pool.submit(disks),
            "gpu": pool.submit(gpu),
            "docker": pool.submit(docker),
            "services": pool.submit(systemd_units),
            "k3s": pool.submit(k3s),
            "backups": pool.submit(backups),
        }
        result = {}
        for key, fut in futures.items():
            try:
                result[key] = fut.result()
            except Exception as exc:  # one failing probe must not blank the page
                result[key] = {"error": f"{type(exc).__name__}: {exc}"}
    result["storage"] = storage_breakdown()
    result["generated_at"] = int(time.time())
    return result


def cached_status() -> dict:
    with _cache_lock:
        if _cache["data"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
            _cache["data"] = collect()
            _cache["at"] = time.time()
        return _cache["data"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/status":
            body = json.dumps(cached_status()).encode()
        elif self.path.split("?")[0] == "/health":
            body = b'{"ok": true}'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet: it's polled every few seconds
        pass


def main() -> None:
    threading.Thread(target=_cpu_sampler, daemon=True).start()
    threading.Thread(target=_du_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
