"""Read-only routes for the Claude desktop connector (connector/). They answer
with text about logged lifting and accept only a bearer token, which opens
these routes and nothing else. With no token configured they don't exist."""

import hmac
from datetime import date

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app import planner_db, workout_chat, workout_import, workouts
from app.config import CONNECTOR_TOKEN

PREFIX = "/connector/"
# A short token could be guessed, so it counts as not configured.
MIN_TOKEN = 32

router = APIRouter()


def refusal(request: Request) -> JSONResponse | None:
    """The error for a connector request that isn't allowed, else None."""
    if len(CONNECTOR_TOKEN) < MIN_TOKEN:
        return JSONResponse({"detail": "The connector isn't set up"}, status_code=404)
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), CONNECTOR_TOKEN.encode()):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    if request.method != "GET":
        return JSONResponse({"detail": "The connector can only read"}, status_code=405)
    return None


def _number(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _set(item: dict) -> str:
    text = workout_chat._set(item)
    if item.get("per_side") is not None:
        text += f", {_number(item['per_side'])} a side"
    detail = [item.get("set_type"), item.get("target") and f"target {item['target']}"]
    detail = [d for d in detail if d]
    return text + (f" [{', '.join(detail)}]" if detail else "")


def session(on: date | None = None) -> str:
    """Every set logged on a day, in order. Without a date, today's; if there
    is none, says so and gives the latest day instead."""
    today = planner_db._today()
    wanted = on or today
    days = [d for d in workouts.history(end=wanted) if d["sets"]]
    if not days:
        return f"No lifting is logged on or before {wanted:%A %B %-d, %Y}."
    day = days[0]
    shown = date.fromisoformat(day["date"])
    lines = []
    if shown != wanted:
        asked = "today" if on is None else f"{wanted:%A %B %-d}"
        lines.append(
            f"Nothing is logged for {asked} ({wanted.isoformat()}). If they lifted then, the spreadsheet still "
            "needs importing on Fitness, Import. The latest earlier workout is below."
        )
    names = list(dict.fromkeys(s["session"] for s in day["sets"] if s["session"]))
    volume = ", ".join(f"{_number(total)} {unit}" for unit, total in day["volume"].items())
    lines.append(
        f"{shown:%A %B %-d, %Y} ({shown.isoformat()}){': ' + ', '.join(names) if names else ''}. "
        f"{len(day['sets'])} sets{', total volume ' + volume if volume else ''}."
    )
    previous = None
    for item in day["sets"]:
        if item["exercise"] != previous:
            previous = item["exercise"]
            lines.append(f"{previous}{' (superset)' if item.get('superset') else ''}:")
            if item.get("note"):
                lines.append(f"  note: {item['note']}")
        lines.append(f"  {_set(item)}")
    return "\n".join(lines)


@router.get("/connector/session")
def get_session(on: date | None = None):
    return {"text": session(on)}


@router.get("/connector/exercise")
def get_exercise(name: str = Query(min_length=1, max_length=100)):
    return {"text": workout_chat.lifts(name)}


@router.get("/connector/bests")
def get_bests():
    listed = workout_import.list_exercises()
    return {"text": workout_chat.lifts(None) if listed else "No lifting has been logged yet."}
