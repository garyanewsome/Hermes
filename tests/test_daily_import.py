"""The daily note importer, on made-up notes written in the real style."""

import os
import unittest
from datetime import date, timedelta
from unittest import mock

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

from app import daily_import, daily_note

TODAY = date(2026, 11, 27)

NOTE = """## 💻 Work
- walk: 99:00 9mi

## 🤖 AI Fitness Dump

### ⚖️ Scale

- Home: 224-5 at 11:42
- PF: At 9:38 a couple of reads but all plus minus about 0.6lb from 225.

### Body Update
- a little stiff

### Gym

- Session: Upper A
- Focus, Feel, Notes:
\t- bench was everything I had
## Workday Micro Sessions

- walk: 30:48 1.23mi
- walk: 42:52 | 1.67mi
- walk:
### Calories

- Time: 19:19 early
- Yesterday's Totals:
\t- Burn:
\t\t- Total: 3,207
\t\t- Active: 818 active
\t- In: 2769
\t- Macros: 196g C / 86g F / 173g P
- Today’s Numbers:
\t- Burn:
\t\t- Total: 2500
\t\t- Active:
\t- In: 1900
\t- Macros: g C / g F / 120g P

## 🤖 Naradi
- walk: 10:00 1mi
"""

BLANK = """## 🤖 AI Fitness Dump
### ⚖️ Scale
- Home: n/a
- PF:
### Gym
- Session:
- Focus, Feel, Notes:
## Workday Micro Sessions
- walk:
### Calories
- Time:
- Yesterday's Totals:
\t- In:
\t- Macros: g C / g F / g P
"""


def note(home="", calories="", walks=""):
    return f"## AI Fitness Dump\n### Scale\n- Home: {home}\n{walks}\n### Calories\n{calories}\n"


class ParserTests(unittest.TestCase):
    def test_a_full_note(self):
        found = daily_note.parse(NOTE)
        self.assertEqual((found["home"]["weight"], found["home"]["candidates"], found["home"]["unsure"]), (224, [224, 225], True))
        self.assertEqual((found["pf"]["weight"], found["pf"]["candidates"]), (225, [225]))
        self.assertEqual((found["body_note"], found["gym_session"]), ("a little stiff", "Upper A"))
        self.assertEqual(found["gym_note"].strip(), "bench was everything I had")
        self.assertEqual([(w["seconds"], w["distance"]) for w in found["walks"]], [(1848, 1.23), (2572, 1.67)])
        self.assertEqual(
            found["calories"]["yesterday"],
            {"burned_total": 3207, "burned_active": 818, "calories_in": 2769, "carbs_g": 196, "fat_g": 86, "protein_g": 173},
        )
        self.assertEqual(found["calories"]["today"], {"burned_total": 2500, "calories_in": 1900, "protein_g": 120})
        self.assertEqual((found["as_of"], found["warnings"]), ("19:19", []))

    def test_a_blank_template_and_no_section(self):
        for text in (BLANK, "## Notes\n- Home: 200\n"):
            found = daily_note.parse(text)
            self.assertEqual(
                (found["home"], found["pf"], found["calories"], found["walks"], found["gym_session"], found["gym_note"]),
                (None, None, {}, [], None, None),
            )

    def test_older_layout_counts_as_today(self):
        found = daily_note.parse(
            "## 🤖 AI Fitness Dump\n### Walks - time | distance\n- Walk 1: 2:21 2.21mi\n"
            "### Calories 19:53\n- Burned:\n\t- Total: 2806\n- In: 1885\n"
        )
        self.assertEqual(found["calories"], {"today": {"burned_total": 2806, "calories_in": 1885}})
        self.assertEqual(found["as_of"], "19:53")
        self.assertIn("minutes a mile", found["warnings"][0])

    def test_weights(self):
        for text, expected in (
            ("228.6 at 10:02", (228.6, [228.6], False)),
            ("226 around 7:15 only about an hour after wake up", (226, [226], False)),
            ("about 227", (227, [227], False)),
            ("226ish around 8am", (226, [226], False)),
            ("230-1", (230, [230, 231], True)),
            ("233/4 - best guess", (233, [233, 234], True)),
            ("231.4 maybe 229 was right", (231.4, [231.4, 229], True)),
            ("forgot again", (None, [], True)),
        ):
            with self.subTest(text=text):
                found = daily_note.weight(text)
                self.assertEqual((found["weight"], found["candidates"], found["unsure"]), expected)
        self.assertIsNone(daily_note.weight("n/a"))

    def test_walks(self):
        for text, expected in (
            ("30.20 1.21mi", (1820, 1.21, "mi")),
            ("30 min, 1.5 mi", (1800, 1.5, "mi")),
            ("56 | 1.32mi", (3360, 1.32, "mi")),
            ("1:02:10 4 km", (3730, 4, "km")),
            ("38:00 1.51mi (watch died 8 min in)", (2280, 1.51, "mi")),
            ("25:00", (1500, None, None)),
        ):
            with self.subTest(text=text):
                found = daily_note.walk(text)
                self.assertEqual((found["seconds"], found["distance"], found["unit"]), expected)
        for text in ("2 part walk", "didn't get a chance for a 3rd walk", "1.2mi"):
            self.assertIsNone(daily_note.walk(text), text)


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import activities, daily_log, planner_db

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db, cls.activities, cls.daily_log = planner_db, activities, daily_log
        app = FastAPI()
        app.include_router(daily_log.router)
        app.include_router(daily_import.router)
        cls.client = TestClient(app)

    def setUp(self):
        self.wipe()
        patcher = mock.patch.object(self.db, "_today", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.wipe()

    def wipe(self):
        with self.db._connect() as conn:
            conn.execute("DELETE FROM daily_log")
            conn.execute("DELETE FROM activities")
            conn.execute("DELETE FROM daily_note_seen")

    def vault(self, notes, status=200):
        response = mock.Mock(status_code=status)
        response.json.return_value = {
            "notes": {daily_import.note_path(day): text for day, text in notes.items()}, "detail": "refused",
        }
        return mock.patch.object(daily_import.httpx, "post", return_value=response)

    def preview(self, notes, days=7):
        with self.vault(notes):
            return self.client.get(f"/daily-import?days={days}").json()["days"]

    def save(self, days):
        body = {"days": [{k: d[k] for k in ("date", "fields", "walks")} for d in days]}
        response = self.client.post("/daily-import", json=body)
        self.assertEqual(response.status_code, 200, response.text)

    def stored(self):
        return {d["date"]: d for d in self.client.get("/daily").json()["days"]}

    def walks(self):
        with self.db._connect() as conn:
            return [(r["duration_seconds"], r["source"]) for r in conn.execute("SELECT * FROM activities ORDER BY id")]

    def test_import_then_nothing_new(self):
        notes = {TODAY: NOTE}
        days = self.preview(notes)
        self.assertEqual([(d["date"], d["status"]) for d in days], [("2026-11-27", "new"), ("2026-11-26", "new")])
        self.assertEqual(self.stored(), {})  # a preview saves nothing
        self.save(days)
        today, yesterday = self.stored()["2026-11-27"], self.stored()["2026-11-26"]
        self.assertEqual((today["weight"], today["weight_pf"], today["calories_partial"], today["calories_as_of"]), (224, 225, True, "19:19"))
        self.assertEqual((yesterday["calories_in"], yesterday["calories_partial"], yesterday["balance"]), (2769, False, -438))
        self.assertEqual(self.walks(), [(1848, "daily-note"), (2572, "daily-note")])
        self.assertEqual([d["status"] for d in self.preview(notes)], ["unchanged", "unchanged"])
        self.save(self.preview(notes))
        self.assertEqual(len(self.walks()), 2)

    def test_unfinished_days_stay_out_of_averages(self):
        self.save(self.preview({TODAY: NOTE}))
        week = self.client.get("/daily").json()["this_week"]
        self.assertEqual((week["average"]["calories_in"], week["counts"]["calories_in"]), (2769, 1))
        self.assertEqual(week["average"]["weight"], 224)

    def test_next_days_totals_finalize_and_are_not_undone(self):
        day = TODAY - timedelta(days=1)
        first = {day: note(calories="- Time: 19:00\n- Today's Numbers:\n\t- In: 1500")}
        self.save(self.preview(first))
        self.assertTrue(self.stored()[day.isoformat()]["calories_partial"])
        both = {**first, TODAY: note(calories="- Yesterday's Totals:\n\t- In: 2600")}
        self.save(self.preview(both))
        got = self.stored()[day.isoformat()]
        self.assertEqual((got["calories_in"], got["calories_partial"], got["calories_as_of"]), (2600, False, None))
        # The older note alone must not put the "so far" number back.
        [again] = self.preview(first)
        self.assertEqual(again["status"], "unchanged")

    def test_older_layout_can_be_counted(self):
        old = {TODAY: note(calories="- Time: 20:00\n- In: 1800")}
        [day] = self.preview(old)
        self.assertTrue(day["fields"]["calories_partial"])
        self.save([day])
        with self.vault(old):
            [again] = self.client.get("/daily-import?days=7&count_old=true").json()["days"]
        self.assertEqual((again["status"], again["fields"]["calories_partial"]), ("changed", False))
        self.save([again])
        self.assertFalse(self.stored()["2026-11-27"]["calories_partial"])
        # A "Today's Numbers" block stays "so far".
        new = {TODAY: note(calories="- Today's Numbers:\n\t- In: 900")}
        self.assertTrue(daily_import.gather(new, True)[TODAY]["fields"]["calories_partial"])

    def test_blank_notes_never_erase_and_hand_entries_survive(self):
        self.client.put("/daily/2026-11-27", json={"weight": 221, "calories_in": 2000, "body_note": "mine"})
        self.activities.add(self.activities.ActivityRequest(activity="Work walk", date=TODAY, minutes=30.8, distance=1.23))
        days = self.preview({TODAY: NOTE.replace("224-5 at 11:42", "")})
        [today] = [d for d in days if d["date"] == "2026-11-27"]
        self.assertEqual((today["status"], today["new_walks"]), ("changed", 1))
        self.assertNotIn("calories_in", today["fields"])  # the stored day is final
        self.save([today])
        got = self.stored()["2026-11-27"]
        self.assertEqual((got["weight"], got["calories_in"], got["weight_pf"]), (221, 2000, 225))
        self.assertEqual(self.walks(), [(1848, None), (2572, "daily-note")])

    def test_editing_a_walk_replaces_only_imported_ones(self):
        self.save(self.preview({TODAY: note(walks="- walk: 30:00 1.2mi\n- walk: 20:00 0.8mi")}))
        self.activities.add(self.activities.ActivityRequest(activity="Bike", date=TODAY, minutes=10))
        [day] = self.preview({TODAY: note(walks="- walk: 30:00 1.2mi\n- walk: 25:00 1.0mi")})
        self.assertEqual((day["new_walks"], day["removed_walks"]), (1, 1))
        self.save([day])
        self.assertEqual(sorted(self.walks(), key=str), sorted([(600, None), (1800, "daily-note"), (1500, "daily-note")], key=str))

    def test_a_typo_in_a_note_does_not_block_the_import(self):
        bad = note(home="200", calories="- Yesterday's Totals:\n\t- Burn:\n\t\t- Total: 100\n\t\t- Active: 900\n\t- In: 99999")
        days = self.preview({TODAY: bad})
        warnings = " ".join(w for d in days for w in d["warnings"])
        self.assertIn("Active calories (900) are more than the total burned (100)", warnings)
        self.assertIn("Calories in 99999 is out of range", warnings)
        self.save(days)
        self.assertEqual(self.stored()["2026-11-27"]["weight"], 200)

    def test_one_bad_day_saves_nothing(self):
        days = [
            {"date": "2026-11-26", "fields": {"weight": 200}, "walks": []},
            {"date": "2026-11-27", "fields": {"burned_total": 100, "burned_active": 200}, "walks": []},
        ]
        self.assertEqual(self.client.post("/daily-import", json={"days": days}).status_code, 400)
        self.assertEqual(self.stored(), {})

    def test_vault_problems(self):
        for status, words in ((404, "needs updating"), (403, "refused")):
            with self.vault({}, status=status):
                response = self.client.get("/daily-import")
            self.assertEqual(response.status_code, 502)
            self.assertIn(words, response.json()["detail"])
        with mock.patch.object(daily_import.httpx, "post", side_effect=daily_import.httpx.ConnectError("x")):
            self.assertEqual(self.client.get("/daily-import").status_code, 502)

    def auto(self, notes):
        with self.vault(notes):
            response = self.client.post("/daily-import/auto")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def put(self, on="2026-11-27", **fields):
        self.assertEqual(self.client.put(f"/daily/{on}", json=fields).status_code, 200)

    def test_auto_saves_clear_values_once(self):
        notes = {TODAY: note(home="226.4 at 7:00", calories="- Today's Numbers:\n\t- In: 900", walks="- walk: 30:00 1.2mi")}
        first = self.auto(notes)
        self.assertEqual((first["saved"], first["review"]), (["2026-11-27"], []))
        got = self.stored()["2026-11-27"]
        self.assertEqual((got["weight"], got["calories_in"], got["calories_partial"]), (226.4, 900, True))
        self.assertEqual(self.auto(notes)["saved"], [])
        self.assertEqual(len(self.walks()), 1)

    def test_auto_leaves_vague_weights_to_pick(self):
        notes = {TODAY: note(home="224-5 at 11:42")}
        result = self.auto(notes)
        self.assertIn("Pick the home weight", result["review"][0]["text"])
        got = self.stored()["2026-11-27"]
        self.assertEqual((got["weight"], got["weight_note"]), (None, "224-5 at 11:42"))
        self.put(weight=225)
        again = self.auto(notes)
        self.assertEqual((again["saved"], again["review"], self.stored()["2026-11-27"]["weight"]), ([], [], 225))

    def test_auto_follows_the_note_until_you_edit_in_naradi(self):
        def notes(eaten, body):
            return {TODAY: f"## AI Fitness Dump\n### Body Update\n- {body}\n### Calories\n- Today's Numbers:\n\t- In: {eaten}\n"}

        self.auto(notes(900, "stiff"))
        self.auto(notes(1500, "stiff"))  # the day goes on
        self.assertEqual(self.stored()["2026-11-27"]["calories_in"], 1500)
        self.put(body_note="my words")
        same = self.auto(notes(1500, "stiff"))
        self.assertEqual((same["saved"], same["review"]), ([], []))
        changed = self.auto(notes(1500, "sore"))
        self.assertIn("Kept your body update", changed["review"][0]["text"])
        self.assertEqual(self.stored()["2026-11-27"]["body_note"], "my words")

    def test_auto_does_not_restore_what_you_cleared_or_deleted(self):
        notes = {TODAY: note(home="226.4", walks="- walk: 30:00 1.2mi")}
        self.auto(notes)
        self.put(weight=None)
        with self.db._connect() as conn:
            conn.execute("DELETE FROM activities")
        self.assertEqual(self.auto(notes)["saved"], [])
        self.assertIsNone(self.stored()["2026-11-27"]["weight"])
        self.assertEqual(self.walks(), [])
        more = {TODAY: note(home="226.4", walks="- walk: 30:00 1.2mi\n- walk: 10:00 0.4mi")}
        self.auto(more)  # a new walk in the note brings the list up to date
        self.assertEqual(len(self.walks()), 2)

    def test_auto_finishes_yesterday_even_if_typed_by_hand(self):
        yesterday = TODAY - timedelta(days=1)
        self.put(yesterday.isoformat(), calories_in=1200, calories_partial=True)
        final = {TODAY: note(calories="- Yesterday's Totals:\n\t- In: 2600")}
        self.auto(final)
        got = self.stored()[yesterday.isoformat()]
        self.assertEqual((got["calories_in"], got["calories_partial"]), (2600, False))
        # A correction to the final number stays, even if marked unfinished again.
        self.put(yesterday.isoformat(), calories_in=2650, calories_partial=True)
        self.auto(final)
        self.assertEqual(self.stored()[yesterday.isoformat()]["calories_in"], 2650)

    def test_auto_respects_what_the_manual_import_changed(self):
        notes = {TODAY: note(home="226.4")}
        [day] = self.preview(notes)
        said = dict(day["fields"])
        day["fields"]["weight"] = 227
        body = {"days": [{"date": day["date"], "fields": day["fields"], "walks": [], "note": said}]}
        self.assertEqual(self.client.post("/daily-import", json=body).status_code, 200)
        result = self.auto(notes)
        self.assertEqual((result["saved"], result["review"], self.stored()["2026-11-27"]["weight"]), ([], [], 227))

    def test_auto_never_overwrites_hand_entries(self):
        self.put(weight=221)
        result = self.auto({TODAY: note(home="226.4")})
        self.assertIn("Kept your home weight", result["review"][0]["text"])
        self.assertEqual(self.stored()["2026-11-27"]["weight"], 221)

    def test_auto_reports_vault_trouble(self):
        with self.vault({}, status=404):
            self.assertEqual(self.client.post("/daily-import/auto").status_code, 502)

    def test_asks_for_the_right_notes(self):
        with self.vault({}) as post:
            self.client.get("/daily-import?days=2")
        self.assertEqual(
            post.call_args.kwargs["json"]["paths"],
            ["00 System/Daily Notes/2026/11/2026-11-27.md", "00 System/Daily Notes/2026/11/2026-11-26.md"],
        )


if __name__ == "__main__":
    unittest.main()
