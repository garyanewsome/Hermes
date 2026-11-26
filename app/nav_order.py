"""The nav menu's order, kept on the server so every device matches."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import planner_db

router = APIRouter()

_KEY = "nav_order"


class NavOrderRequest(BaseModel):
    # Menu item keys, top first. The frontend owns the list of items, so
    # unknown or missing keys are fine here; an empty list means the default.
    order: list[str] = Field(max_length=50)


@router.get("/nav-order")
def get_nav_order():
    return {"order": planner_db.get_setting(_KEY, [])}


@router.put("/nav-order")
def put_nav_order(request: NavOrderRequest):
    order = list(dict.fromkeys(key for key in request.order if 0 < len(key) <= 40))
    planner_db.set_setting(_KEY, order)
    return {"order": order}
