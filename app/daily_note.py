"""Reads the "AI Fitness Dump" section of a daily note, as it is actually
typed: loose weigh-ins, yesterday's calorie totals and today's so far, gym
notes and walk times. Pure text in, plain data out; nothing is guessed that
the preview can't show."""

import re

_START = re.compile(r"^##(?!#).*fitness dump", re.IGNORECASE)
# A level-2 heading the template puts inside the fitness section.
_INSIDE = re.compile(r"micro sessions", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
_BULLET = re.compile(r"^(\s*)(?:[-*+]\s+)?(?:\[[ xX]\]\s*)?(.*)$")
_TIME = re.compile(r"(?<![\d.])([01]?\d|2[0-3]):[0-5]\d(?!\d)")
_EMPTY = {"", "n/a", "na", "none", "-"}
WEIGHT_RANGE = (80, 500)


def weight(text: str) -> dict | None:
    """The numbers in a weigh-in line that could be the weight, best guess
    first, with the whole line kept as its note."""
    cleaned = " ".join(text.split())
    if cleaned.casefold() in _EMPTY:
        return None
    # Clock times and small amounts ("0.6lb") aren't weights.
    numbers = _TIME.sub(" ", cleaned)
    found: list[float] = []
    for match in re.finditer(r"(?<![\d.])(\d{2,3}(?:\.\d+)?)(?:\s*[-–/]\s*(\d{1,3}(?:\.\d+)?))?(?![\d.]*\s*(?:am|pm|min|g\b|%))", numbers, re.IGNORECASE):
        first, second = match.group(1), match.group(2)
        values = [float(first)]
        if second is not None:
            # "224-5" means 224 to 225.
            whole = second.split(".")[0]
            if len(whole) < len(first.split(".")[0]):
                second = first.split(".")[0][: -len(whole)] + second
            values.append(float(second))
        found += [v for v in values if WEIGHT_RANGE[0] <= v <= WEIGHT_RANGE[1] and v not in found]
    # "226ish" has one reading; only a line with several (or none) needs a pick.
    return {"weight": found[0] if found else None, "candidates": found, "unsure": len(found) != 1, "note": cleaned}


def _count(text: str) -> float | None:
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    return None if not match else float(match.group().replace(",", ""))


def macros(text: str) -> dict:
    """"196g C / 86g F / 173g P", in any order. A blank slot is left out."""
    found = {}
    for number, letter in re.findall(r"(\d+(?:\.\d+)?)\s*g?\s*([CFP])(?![a-z])", text, re.IGNORECASE):
        found[{"c": "carbs_g", "f": "fat_g", "p": "protein_g"}[letter.casefold()]] = float(number)
    return found


def walk(text: str) -> dict | None:
    """"30:48 1.23mi", "42:52 | 1.67mi" or "30 min, 1.5 mi". Needs a time."""
    distance = unit = None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(miles?|mi|kms?)\b", text, re.IGNORECASE)
    if match:
        distance, unit = float(match.group(1)), "km" if match.group(2).lower().startswith("k") else "mi"
        text = text[: match.start()] + " " + text[match.end():]
    seconds = None
    clock = re.search(r"(?<![\d.])(?:(\d{1,2}):)?(\d{1,3})[:.]([0-5]\d)(?!\d)", text)
    minutes = re.search(r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m)\b", text, re.IGNORECASE)
    # The first one written is the walk's time; later ones are commentary.
    if clock and (not minutes or clock.start() < minutes.start()):
        seconds = int(clock.group(1) or 0) * 3600 + int(clock.group(2)) * 60 + int(clock.group(3))
    elif minutes:
        seconds = round(float(minutes.group(1)) * 60)
    elif distance is not None:
        bare = re.match(r"\s*(\d{1,3})\s*(?:\||,|$)", text)  # "56 | 1.32mi"
        seconds = int(bare.group(1)) * 60 if bare else None
    if not seconds or seconds > 86400:
        return None
    if distance is not None and not 0 < distance <= 1000:
        distance = unit = None
    return {"seconds": seconds, "distance": distance, "unit": unit}


def _section(text: str) -> list[str]:
    lines = text.replace("’", "'").split("\n")
    for index, line in enumerate(lines):
        if _START.match(line.strip()):
            out = []
            for following in lines[index + 1:]:
                heading = _HEADING.match(following)
                if heading and len(heading.group(1)) <= 2 and not _INSIDE.search(heading.group(2)):
                    break
                out.append(following)
            return out
    return []


def parse(text: str) -> dict:
    """{"home", "pf", "body_note", "gym_session", "gym_note", "calories":
    {"yesterday"|"today": {...}}, "as_of", "walks", "warnings"}. Empty parts
    are None or empty. Older notes with one calorie block count as "today"."""
    # "dated" turns true when the calories say which day they are for.
    result = {"home": None, "pf": None, "calories": {}, "as_of": None, "walks": [], "warnings": [], "dated": False}
    body, gym, session = [], [], None
    area, block = "", "today"
    for raw in _section(text):
        heading = _HEADING.match(raw)
        if heading:
            area = re.sub(r"^[^\w]+", "", heading.group(2)).casefold()
            block = "today"
            if area.startswith("calories") and _TIME.search(area):
                result["as_of"] = _TIME.search(area).group()
            continue
        indent, line = _BULLET.match(raw).groups()
        line = line.strip()
        if not line:
            continue
        key, colon, value = line.partition(":")
        key, value = key.strip().casefold(), value.strip()
        if colon and re.fullmatch(r"walk(?:\s*\d+)?", key):
            if value.casefold() not in _EMPTY:
                found = walk(value)
                if found:
                    result["walks"].append({**found, "text": value})
                    pace = found["seconds"] / 60 / found["distance"] if found["distance"] else None
                    if pace and found["unit"] == "mi" and not 10 <= pace <= 60:
                        result["warnings"].append(f"Check walk \"{value}\": that's {pace:.0f} minutes a mile")
                else:
                    result["warnings"].append(f"Walk \"{value}\" has no time I can read, so it was skipped")
        elif area.endswith("scale"):
            if colon and key in ("home", "pf"):
                result[key] = weight(value)
        elif area.startswith("body"):
            body.append(line)
        elif area.startswith("gym"):
            if colon and key == "session":
                session = value or None
            elif colon and key.startswith("focus"):
                if value:
                    gym.append(value)
            else:
                gym.append(("  " if len(indent.expandtabs(2)) > 2 else "") + line)
        elif area.startswith("calories"):
            if key.startswith("yesterday"):
                block, result["dated"] = "yesterday", True
            elif key.startswith("today"):
                block, result["dated"] = "today", True
            elif key == "time" or key.startswith(("as of", "@")):
                found = _TIME.search(line)
                result["as_of"] = found.group() if found else result["as_of"]
            elif key in ("total", "active", "in"):
                number = _count(value)
                if number is not None:
                    field = {"total": "burned_total", "active": "burned_active", "in": "calories_in"}[key]
                    result["calories"].setdefault(block, {})[field] = number
            elif key == "macros":
                found = macros(value)
                if found:
                    result["calories"].setdefault(block, {}).update(found)
    result["body_note"] = "\n".join(body) or None
    result["gym_session"] = session
    result["gym_note"] = "\n".join(gym).strip("\n") or None
    return result
