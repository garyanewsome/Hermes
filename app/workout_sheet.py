"""Reads the training spreadsheet (an .xlsx export). Pure code, no storage.

Layout: one tab per session type. Columns A-D are exercise, set type, planned
sets and target reps. To the right, one block of columns per date, each headed
by "Date:" in row 1 and its own Weight / Reps / Myo / Volume / Total Vol.
headings in row 2. The three weight columns hold either one weight, or base
weight / per side / total for plate machines (announced by a "per side" row
above the exercise). Rows run down to "Total Sets".

The Myo column breaks a set's total down: "12 + 3" is 12 reps, a rest-pause,
then 3 more; "30 ++ 10" is 30 full reps then 10 partials. Both can appear
("12 + 3 ++ 4"). Reps holds the total, so partials count toward volume. An
older "x" marks a set without giving the split.

Errors block saving. Warnings describe cells that were skipped or read loosely,
so they can be fixed in the sheet and uploaded again."""

import io
import re
from datetime import date, datetime, timedelta

import openpyxl

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 500
MAX_COLUMNS = 400
# Base weight multiplier, by the header above a plate machine: two arms each
# carry the arm weight; a sled is a single weight.
BASE_FACTORS = {"arm / each": 2, "arm/each": 2, "arms": 2, "arm": 2, "sled": 1}
SET_TYPES = {"top et": "top set", "top": "top set", "mini": "mini set", "mini sets": "mini set", "drop": "drop set"}


class SheetError(ValueError):
    pass


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = _text(value)
        if not re.fullmatch(r"\d{1,6}(\.\d{1,3})?", text):
            return None
        number = float(text)
    return number if 0 <= number < 100_000 else None


def _label(value) -> str:
    """A cell as shown: 8.0 reads as "8"."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value)


def _parse_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    match = re.fullmatch(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", _text(value))
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


class _Sheet:
    def __init__(self, ws):
        self.ws = ws
        self.rows = min(ws.max_row, MAX_ROWS)
        self.columns = min(ws.max_column, MAX_COLUMNS)
        # B and D are often one cell merged down several sets.
        self.merged = {}
        for area in ws.merged_cells.ranges:
            if area.min_col == area.max_col and area.min_col in (2, 4):
                for row in range(area.min_row, min(area.max_row, MAX_ROWS) + 1):
                    self.merged[(row, area.min_col)] = (area.min_row, area.min_col)

    def value(self, row, column):
        return self.ws.cell(row, column).value

    def inherited(self, row, column):
        return self.value(*self.merged.get((row, column), (row, column)))


def _blocks(sheet: _Sheet) -> list[dict]:
    starts = [c for c in range(1, sheet.columns + 1) if _text(sheet.value(1, c)).lower().startswith("date")]
    blocks = []
    for index, start in enumerate(starts):
        stop = starts[index + 1] if index + 1 < len(starts) else sheet.columns + 1
        headings = {}
        for column in range(start, stop):
            heading = _text(sheet.value(2, column)).lower()
            if heading:
                headings.setdefault(heading, column)
        dates = [sheet.value(1, c) for c in range(start + 1, stop) if _text(sheet.value(1, c))]
        blocks.append({"start": start, "headings": headings, "date": dates[0] if dates else None})
    return blocks


def _rows(sheet: _Sheet, blocks: list[dict], end: int) -> list[dict]:
    """Assigns each row to an exercise, shared by every date block."""
    out = []
    exercise = None
    plate_row = None
    superset_next = False
    order = 0
    for row in range(3, end):
        name = " ".join(_text(sheet.value(row, 1)).split())
        per_side_header = any(_text(sheet.value(row, b["start"] + 1)).lower() == "per side" for b in blocks)
        if per_side_header:
            plate_row = row
            continue
        if name.startswith("~"):
            if "superset" in name.lower() and exercise:
                exercise["superset"] = True
                superset_next = True
            continue
        if name:
            order += 1
            exercise = {"name": name, "order": order, "planned_sets": _number(sheet.value(row, 3)),
                        "plate_row": plate_row, "first_row": row, "superset": superset_next}
            plate_row, superset_next = None, False
        if exercise:
            out.append({"row": row, "exercise": exercise,
                        "set_type": _text(sheet.inherited(row, 2)), "target": _label(sheet.inherited(row, 4))})
    return out


def _read_block(sheet, block, rows, end, label, warnings) -> list[dict]:
    headings = block["headings"]
    reps_col = headings["reps"]
    weight_cols = list(range(block["start"], reps_col))
    sets = []
    notes = {}
    for entry in rows:
        row, exercise = entry["row"], entry["exercise"]
        where = f"{label}, row {row} ({exercise['name']})"
        raw_reps = sheet.value(row, reps_col)
        myo_raw = _label(sheet.value(row, headings["myo"])) if "myo" in headings else ""
        myo = bool(myo_raw)
        cells = [sheet.value(row, c) for c in weight_cols]
        words = [_text(c) for c in cells if _text(c) and _number(c) is None]
        if words:
            notes.setdefault(exercise["order"], []).extend(words)
            warnings.append(f"{where}: note in a weight cell: '{'; '.join(words)}'")

        plate = exercise["plate_row"] is not None and len(weight_cols) >= 3
        weight = per_side = base = base_kind = None
        if plate:
            base_kind = _text(sheet.value(exercise["plate_row"], weight_cols[0])).lower() or None
            base = _number(sheet.value(exercise["first_row"], weight_cols[0]))
            per_side = _number(cells[1])
            cached_total = _number(cells[2])
            factor = BASE_FACTORS.get(base_kind)
            if per_side is not None and factor and base is not None:
                weight = factor * base + 2 * per_side
                if cached_total is not None and abs(cached_total - weight) > 0.01:
                    warnings.append(f"{where}: sheet total weight {cached_total:g} but base + plates is {weight:g}")
            elif per_side is not None:
                weight = cached_total
                if weight is None:
                    warnings.append(f"{where}: can't work out the total weight (header '{base_kind}')")
        else:
            weight = next((n for n in map(_number, cells) if n is not None), None)

        if not _text(raw_reps):
            entered = per_side if plate else weight
            if myo or (entered is not None and block["has_reps"]):
                warnings.append(f"{where}: no reps, so this set was skipped")
            continue
        reps = _number(raw_reps)
        reps_raw = _label(raw_reps)
        breakdown = parse_breakdown(myo_raw)
        typed = parse_breakdown(reps_raw)
        if typed:
            # A breakdown in the wrong column: add it up rather than lose reps.
            reps = float(sum(typed.values()))
            breakdown = breakdown or typed
            warnings.append(f"{where}: reps '{reps_raw}' read as {reps:g}; put the total in Reps and the split "
                            "in Myo so the sheet's volume is right")
        if reps is None:
            loose = re.match(r"\d{1,4}", reps_raw)
            if not loose:
                warnings.append(f"{where}: reps '{reps_raw}' isn't a number, so this set was skipped")
                continue
            reps = float(loose.group())
            warnings.append(f"{where}: reps '{reps_raw}' read as {loose.group()}")
        if not reps.is_integer() or reps > 1000:
            warnings.append(f"{where}: reps '{reps_raw}' isn't a whole number up to 1000, so this set was skipped")
            continue
        if reps == 0:
            warnings.append(f"{where}: 0 reps, treated as not done")
            continue
        if breakdown and sum(breakdown.values()) != reps:
            warnings.append(f"{where}: Myo '{myo_raw}' adds up to {sum(breakdown.values())} but Reps is "
                            f"{reps:g}; kept Reps, without the split")
            breakdown = None
        elif myo_raw and not breakdown and myo_raw.lower() != "x":
            warnings.append(f"{where}: Myo '{myo_raw}' should look like '12 + 3' or '30 ++ 10'; kept as typed")
        set_type = " ".join(entry["set_type"].lower().split())
        planned = exercise["planned_sets"]
        sets.append({
            "exercise": exercise["name"], "exercise_order": exercise["order"],
            "set_type": SET_TYPES.get(set_type, set_type) or None,
            "target": entry["target"] or None,
            "planned_sets": int(planned) if planned is not None and planned.is_integer() and planned < 1000 else None,
            "superset": exercise["superset"],
            "weight": weight, "per_side": per_side, "base_weight": base if plate else None,
            "base_kind": base_kind, "reps": int(reps), "reps_raw": reps_raw, "myo": myo,
            "myo_raw": myo_raw or None,
            **(breakdown or {"full_reps": None, "rest_pause_reps": None, "partial_reps": None}),
        })
    for item in sets:
        item["note"] = "; ".join(notes.get(item["exercise_order"], [])) or None
    return sets


def parse_breakdown(text: str) -> dict | None:
    """Splits "12 + 3 ++ 4" into full, rest-pause (+) and partial (++) reps.
    Returns None if the text isn't a breakdown."""
    text = text.strip()
    if not re.fullmatch(r"\d{1,4}(\s*\+{1,2}\s*\d{1,4})+", text):
        return None
    parts = {"full_reps": int(re.match(r"\d+", text).group()), "rest_pause_reps": 0, "partial_reps": 0}
    for sign, count in re.findall(r"(\++)\s*(\d+)", text):
        parts["partial_reps" if sign == "++" else "rest_pause_reps"] += int(count)
    return parts


def totals(sets: list[dict]) -> dict:
    """volume counts the full load; entered_volume counts the weight as typed
    (per side on plate machines)."""
    full = sum((s["weight"] or 0) * s["reps"] for s in sets)
    entered = sum(((s["per_side"] if s["base_kind"] else s["weight"]) or 0) * s["reps"] for s in sets)
    return {"set_count": len(sets), "volume": round(full, 2), "entered_volume": round(entered, 2)}


def parse(data: bytes, today: date) -> dict:
    """Returns {"workouts": [...], "errors": [str], "warnings": [str],
    "skipped_tabs": [str]}."""
    if len(data) > MAX_FILE_BYTES:
        raise SheetError("That file is larger than 5 MB")
    try:
        book = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as exc:
        raise SheetError("Couldn't open that file; upload an .xlsx export of the sheet") from exc

    workouts, errors, warnings, skipped = [], [], [], []
    seen = set()
    for ws in book.worksheets:
        if ws.sheet_state != "visible":
            skipped.append(f"{ws.title} (hidden)")
            continue
        sheet = _Sheet(ws)
        blocks = _blocks(sheet)
        end = next((r for r in range(3, sheet.rows + 1) if _text(sheet.value(r, 1)).lower() == "total sets"), None)
        if not blocks or end is None:
            skipped.append(f"{ws.title} (needs a 'Date:' heading and a 'Total Sets' row)")
            continue
        rows = _rows(sheet, blocks, end)
        for block in blocks:
            if block["date"] is None:
                continue  # prefilled for next time
            label = f"{ws.title} {_label(block['date'])}"
            day = _parse_date(block["date"])
            if day is None:
                errors.append(f"{label}: date should look like 2026.11.25")
                continue
            if day > today + timedelta(days=1):
                errors.append(f"{label}: date is in the future")
                continue
            if "reps" not in block["headings"]:
                errors.append(f"{label}: no 'Reps' heading in row 2")
                continue
            if (ws.title, day) in seen:
                errors.append(f"{label}: this date appears twice on this tab")
                continue
            seen.add((ws.title, day))
            reps_col = block["headings"]["reps"]
            block["has_reps"] = any(_text(sheet.value(r["row"], reps_col)) for r in rows)
            if not block["has_reps"]:
                warnings.append(f"{label}: dated but has no reps yet, so it was skipped")
                continue
            sets = _read_block(sheet, block, rows, end, label, warnings)
            if not sets:
                continue
            workout = {"session": ws.title.strip(), "date": day.isoformat(), "sets": sets, **totals(sets)}
            for heading, key in (("total vol.", "volume"), ("volume", "entered_volume")):
                column = block["headings"].get(heading)
                shown = _number(sheet.value(end, column)) if column else None
                if shown is not None and abs(shown - workout[key]) > 0.01:
                    warnings.append(
                        f"{label}: sheet's '{heading}' total is {shown:g} but its sets add up to {workout[key]:g}"
                    )
            workouts.append(workout)

    if not workouts and not errors:
        errors.append("No dated workouts with reps were found")
    workouts.sort(key=lambda w: (w["date"], w["session"]))
    return {"workouts": workouts, "errors": errors, "warnings": warnings, "skipped_tabs": skipped}
