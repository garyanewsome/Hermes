"""Data for the System page.

Two sources, kept separate so one being down never blanks the other:

- the host status service (statusd/homelab_status.py) for what only the host
  can see: disks, load, temperatures, GPU, Docker, systemd, K3s pods;
- direct "is it answering?" probes from Hermes itself to each app, plus
  Ollama's own /api/ps for which model currently holds the GPU.

Everything here is read-only.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from app import planner_db
from app.config import (
    ATHENAEUM_HOST_HEADER,
    ATHENAEUM_URL,
    CODEBASE_SEARCHER_URL,
    HINDSIGHT_URL,
    IMAGES_AFTER_DARK_URL,
    IRIS_URL,
    KAVITA_URL,
    OLLAMA_HOST,
    SEARXNG_URL,
    SYSTEM_STATUS_URL,
)

logger = logging.getLogger("hermes")

PROBE_TIMEOUT = 3.0


def _http_probe(name: str, url: str, headers: dict | None = None) -> dict:
    """'Answering' = got any HTTP response below 500. A 404 on a root URL is a
    perfectly healthy service that just has no page there."""
    started = time.monotonic()
    try:
        resp = httpx.get(url, headers=headers, timeout=PROBE_TIMEOUT, follow_redirects=False)
        ms = round((time.monotonic() - started) * 1000)
        return {"name": name, "ok": resp.status_code < 500, "ms": ms, "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"name": name, "ok": False, "ms": None, "detail": type(exc).__name__}


def _postgres_probe() -> dict:
    started = time.monotonic()
    try:
        with planner_db._connect() as conn:
            conn.execute("SELECT 1")
        return {"name": "Planner database", "ok": True, "ms": round((time.monotonic() - started) * 1000), "detail": "query ok"}
    except Exception as exc:
        return {"name": "Planner database", "ok": False, "ms": None, "detail": type(exc).__name__}


def _probes() -> list[dict]:
    jobs = [
        lambda: _http_probe("Ollama", f"{OLLAMA_HOST}/api/version"),
        lambda: _http_probe("Iris (images)", f"{IRIS_URL}/health"),
        lambda: _http_probe("images-after-dark", f"{IMAGES_AFTER_DARK_URL}/health"),
        lambda: _http_probe("Hindsight (memory)", f"{HINDSIGHT_URL}/health"),
        lambda: _http_probe("Athenaeum (notes)", f"{ATHENAEUM_URL}/health", {"Host": ATHENAEUM_HOST_HEADER}),
        lambda: _http_probe("CodebaseSearcher", f"{CODEBASE_SEARCHER_URL}/health"),
        lambda: _http_probe("SearXNG (web search)", f"{SEARXNG_URL}/"),
        lambda: _http_probe("Kavita (library)", f"{KAVITA_URL}/api/health"),
        _postgres_probe,
    ]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return [f.result() for f in [pool.submit(j) for j in jobs]]


def _ollama_loaded() -> list[dict]:
    try:
        resp = httpx.get(f"{OLLAMA_HOST}/api/ps", timeout=PROBE_TIMEOUT)
        resp.raise_for_status()
        return [
            {
                "name": m.get("name"),
                "size": m.get("size"),
                "size_vram": m.get("size_vram"),
                "expires_at": m.get("expires_at"),
            }
            for m in resp.json().get("models", [])
        ]
    except Exception:
        return []


def _agent() -> tuple[dict | None, str | None]:
    try:
        resp = httpx.get(f"{SYSTEM_STATUS_URL}/status", timeout=15.0)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        logger.warning("Host status service unavailable: %s", exc)
        return None, f"{type(exc).__name__}"


def get_system() -> dict:
    with ThreadPoolExecutor(max_workers=3) as pool:
        agent_f, probes_f, ollama_f = pool.submit(_agent), pool.submit(_probes), pool.submit(_ollama_loaded)
        agent, agent_error = agent_f.result()
        return {
            "agent": agent,
            "agent_error": agent_error,
            "probes": probes_f.result(),
            "ollama_loaded": ollama_f.result(),
            "generated_at": int(time.time()),
        }
