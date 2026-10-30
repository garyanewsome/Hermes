"""Checks that a service is *working*, not just *answering*.

system_status._probes() asks each service "are you up?", and that is not
enough: Hindsight reported `healthy` for nine days while every call that
needed its LLM returned 404, because its configured model had been removed
from Ollama. The checks here exercise the failing path itself:

- every model Hermes is configured to use is actually installed in Ollama;
- vault-keeper can reach the vault's git remote with its deploy key;
- Hindsight can run its own fact extraction end to end. This uses its
  dry-run-extract endpoint, which calls the LLM but stores nothing.

The extraction check takes ~15s and loads a model, so it runs on a timer in
a background thread and callers read the last result.
"""

import logging
import threading
import time

import httpx

from app.config import AUDIO_MODEL, CHAT_MODEL, HINDSIGHT_BANK_ID, HINDSIGHT_URL, OLLAMA_HOST, VAULT_KEEPER_URL

logger = logging.getLogger("hermes")

INTERVAL_SECONDS = 30 * 60
EXTRACT_TIMEOUT = 120.0
CANARY_TEXT = "Gary decided on 2026-01-15 to use CMake for the build system."

_lock = threading.Lock()
_results: dict[str, dict] = {}
_started_at = time.time()


def _check_models() -> dict:
    try:
        resp = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        resp.raise_for_status()
        installed = {m["name"] for m in resp.json().get("models", [])}
    except Exception as exc:
        return {"ok": False, "text": f"Can't list Ollama's models ({type(exc).__name__})"}
    wanted = {"chat": CHAT_MODEL, "audio": AUDIO_MODEL}
    missing = sorted({m for m in wanted.values() if m not in installed})
    if missing:
        return {"ok": False, "text": f"Hermes is set to use {', '.join(missing)}, which Ollama doesn't have"}
    return {"ok": True, "text": "Configured models are installed"}


def _check_hindsight_extraction() -> dict:
    url = f"{HINDSIGHT_URL}/v1/default/banks/{HINDSIGHT_BANK_ID}/memories/dry-run-extract"
    try:
        resp = httpx.post(url, json={"content": CANARY_TEXT}, timeout=EXTRACT_TIMEOUT)
    except Exception as exc:
        return {"ok": False, "text": f"Hindsight memory extraction didn't respond ({type(exc).__name__})"}
    if resp.status_code != 200:
        detail = resp.text[:160].replace("\n", " ")
        return {"ok": False, "text": f"Hindsight can't extract memories (HTTP {resp.status_code}: {detail})"}
    if not resp.json().get("facts"):
        return {"ok": False, "text": "Hindsight's model returned no facts for a test sentence"}
    return {"ok": True, "text": "Hindsight extraction works"}


def _check_vault_keeper() -> dict:
    # /health only says vault-keeper is up. /health/deep asks the vault's git
    # remote with the same deploy key a write uses, so a revoked key or a
    # broken network shows here instead of as every note save failing.
    try:
        resp = httpx.get(f"{VAULT_KEEPER_URL}/health/deep", timeout=20.0)
    except Exception as exc:
        return {"ok": False, "text": f"vault-keeper didn't respond ({type(exc).__name__})"}
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", "")
        except ValueError:
            detail = resp.text
        return {"ok": False, "text": f"vault-keeper can't reach the vault on GitHub (HTTP {resp.status_code}: {str(detail)[:160]})"}
    return {"ok": True, "text": "vault-keeper can reach the vault"}


CHECKS = {
    "models": _check_models,
    "vault_keeper": _check_vault_keeper,
    "hindsight_extraction": _check_hindsight_extraction,
}


def run_all() -> None:
    for name, fn in CHECKS.items():
        try:
            result = fn()
        except Exception as exc:  # a check must never kill the thread
            logger.exception("health check %s crashed", name)
            result = {"ok": False, "text": f"Check {name} crashed ({type(exc).__name__})"}
        result["checked_at"] = int(time.time())
        with _lock:
            _results[name] = result
        if not result["ok"]:
            logger.warning("health check %s failed: %s", name, result["text"])


def _loop() -> None:
    while True:
        run_all()
        time.sleep(INTERVAL_SECONDS)


def start_background() -> None:
    threading.Thread(target=_loop, name="health-checks", daemon=True).start()


def get_alerts() -> list[dict]:
    """Current problems, shaped for the UI: [{id, level, text}]. Empty means
    all clear. Checks that haven't finished their first run yet say nothing."""
    now = time.time()
    with _lock:
        results = dict(_results)
    alerts = []
    for name, r in results.items():
        if not r["ok"]:
            alerts.append({"id": name, "level": "bad", "text": r["text"]})
        elif now - r["checked_at"] > INTERVAL_SECONDS * 2.5:
            alerts.append({"id": f"{name}-stale", "level": "warn", "text": f"Health check '{name}' hasn't run since it last passed"})
    if not results and now - _started_at > INTERVAL_SECONDS:
        alerts.append({"id": "checks-never-ran", "level": "warn", "text": "Background health checks have not completed"})
    return alerts
