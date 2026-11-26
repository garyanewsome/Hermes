"""Spreadsheet import, against a small workbook built to mirror the real one."""

import io
import os
import unittest
from datetime import date

import openpyxl

from app import workout_sheet

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL

TODAY = date(2026, 11, 26)


def build(edit=None, day="2020.01.05") -> bytes:
    book = openpyxl.Workbook()
    ws = book.active
    ws.title = "UPPER A"
    cells = {
        "E1": "Date:", "I1": day, "L1": "Date:",
        "E2": "Weight", "H2": "Reps", "I2": "Myo", "J2": "Volume", "K2": "Total Vol.",
        "L2": "Weight", "O2": "Reps", "P2": "Myo", "Q2": "Volume", "R2": "Total Vol.",
        "A4": "Dead Hang",
        "A6": "Close Grip Pulls", "B6": "mini sets", "C6": 3, "D6": "fail", "H6": "3", "H7": "3ish",
        "E9": "arm / each", "F9": "per side", "G9": "total weight",
        "A10": "Flat Bench", "B10": "top set", "C10": 2, "D10": "5-7", "E10": "10", "F10": "105", "G10": 230, "H10": "7",
        "B11": "back off", "D11": 8.0, "F11": 90, "G11": 200, "H11": 6, "I11": "x",
        "M10": "105",
        "A13": "Leg Extensions", "B13": "top et", "F13": "180", "H13": "10",
        "A14": "~~~ superset ~~~",
        "A15": "Bodyweight Squats", "H15": "12",
        "A17": "Assisted Pull Ups", "H17": "8", "F18": "both taken",
        "A20": "Abductors", "F20": "120", "H20": "0",
        "A22": "Total Sets", "J22": 2610, "K22": 4610,
    }
    for address, value in cells.items():
        ws[address] = value
    ws.merge_cells("B6:B7")
    if edit:
        edit(book)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def parse(data):
    return workout_sheet.parse(data, TODAY)


class SheetTests(unittest.TestCase):
    def test_reads_the_dated_block(self):
        result = parse(build())
        self.assertEqual(result["errors"], [])
        [workout] = result["workouts"]
        self.assertEqual((workout["session"], workout["date"]), ("UPPER A", "2020-01-05"))
        sets = workout["sets"]
        self.assertEqual(
            [(s["exercise"], s["reps"]) for s in sets],
            [("Close Grip Pulls", 3), ("Close Grip Pulls", 3), ("Flat Bench", 7), ("Flat Bench", 6),
             ("Leg Extensions", 10), ("Bodyweight Squats", 12), ("Assisted Pull Ups", 8)],
        )
        self.assertEqual([s["set_type"] for s in sets[:2]], ["mini set", "mini set"])
        self.assertEqual(sets[1]["reps_raw"], "3ish")
        bench = sets[2]
        self.assertEqual((bench["weight"], bench["per_side"], bench["base_weight"]), (230, 105, 10))
        self.assertEqual((sets[3]["target"], sets[3]["myo"], sets[3]["planned_sets"]), ("8", True, 2))
        self.assertEqual((sets[4]["set_type"], sets[4]["weight"], sets[4]["base_kind"]), ("top set", 180, None))
        self.assertEqual([s["superset"] for s in sets[4:]], [True, True, False])
        self.assertEqual((sets[6]["weight"], sets[6]["note"]), (None, "both taken"))
        # 230*7 + 200*6 + 180*10, and per side 105*7 + 90*6 + 180*10
        self.assertEqual((workout["volume"], workout["entered_volume"]), (4610, 3075))

    def test_warns_about_loose_and_skipped_cells_and_wrong_totals(self):
        warnings = "\n".join(parse(build())["warnings"])
        for expected in ("'3ish' read as 3", "0 reps", "both taken", "'volume' total is 2610"):
            self.assertIn(expected, warnings)
        self.assertNotIn("'total vol.' total", warnings)

    def bench_sets(self, reps, myo):
        def edit(book):
            book.active["H10"] = reps
            book.active["I10"] = myo
        result = parse(build(edit))
        sets = [s for s in result["workouts"][0]["sets"] if s["exercise"] == "Flat Bench"]
        return sets[0], [w for w in result["warnings"] if "row 10" in w]

    def split(self, item):
        return item["reps"], item["full_reps"], item["rest_pause_reps"], item["partial_reps"]

    def test_myo_breakdowns(self):
        for reps, myo, expected in (
            ("15", "12 + 3", (15, 12, 3, 0)),
            ("40", "30 ++ 10", (40, 30, 0, 10)),
            (19, "12+3++4", (19, 12, 3, 4)),
            ("17", "12 + 3 + 2", (17, 12, 5, 0)),
        ):
            with self.subTest(myo=myo):
                item, warnings = self.bench_sets(reps, myo)
                self.assertEqual((self.split(item), item["myo_raw"], warnings), (expected, myo, []))

    def test_old_x_mark_has_no_split_and_no_warning(self):
        item, warnings = self.bench_sets("7", "x")
        self.assertEqual((item["myo"], self.split(item), warnings), (True, (7, None, None, None), []))

    def test_breakdown_that_disagrees_or_is_unreadable(self):
        for myo, expected in (("12 + 3", "adds up to 15"), ("12 +++ 3", "should look like"), ("+3", "should look like")):
            with self.subTest(myo=myo):
                item, warnings = self.bench_sets("14", myo)
                self.assertEqual((self.split(item), item["myo_raw"]), ((14, None, None, None), myo))
                self.assertIn(expected, warnings[0])

    def test_breakdown_typed_in_reps_is_added_up(self):
        item, warnings = self.bench_sets("30 ++ 10", None)
        self.assertEqual(self.split(item), (40, 30, 0, 10))
        self.assertIn("read as 40", warnings[0])

    def test_sled_base_counts_once(self):
        def edit(book):
            book.active["E9"] = "sled"
        bench = parse(build(edit))["workouts"][0]["sets"][2]
        self.assertEqual(bench["weight"], 220)

    def test_bad_dates_are_errors(self):
        for day in ("soon", "2020.02.30", "2027.01.01"):
            with self.subTest(day=day):
                self.assertTrue(parse(build(day=day))["errors"])

    def test_same_date_twice_is_an_error(self):
        def edit(book):
            book.active["P1"] = "2020.01.05"
        self.assertIn("twice", parse(build(edit))["errors"][0])

    def test_other_tabs_are_skipped(self):
        result = parse(build(lambda book: book.create_sheet("Notes")))
        self.assertEqual(len(result["workouts"]), 1)
        self.assertIn("Notes", result["skipped_tabs"][0])

    def test_not_a_spreadsheet(self):
        with self.assertRaises(workout_sheet.SheetError):
            parse(b"hello")


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app import planner_db, workout_import, workouts

        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        planner_db.init_planner_db()
        cls.db = planner_db
        app = FastAPI()
        app.include_router(workouts.router)
        app.include_router(workout_import.router)
        cls.client = TestClient(app)

    def setUp(self):
        with self.db._connect() as conn:
            for table in ("lift_sets", "activities", "walks", "workout_pastes", "workouts", "workout_programs", "exercise_aliases"):
                conn.execute(f"DELETE FROM {table}")

    tearDown = setUp

    def upload(self, data, path="/workouts/import", name="Winter.xlsx"):
        return self.client.post(path, files={"file": (name, data)})

    def days(self):
        return self.client.get("/workouts").json()["days"]

    def test_preview_saves_nothing(self):
        body = self.upload(build(), "/workouts/import/preview").json()
        self.assertEqual(body["program"], "Winter")
        self.assertIn("Flat Bench", body["new_exercises"])
        self.assertEqual(self.days(), [])

    def test_upload_twice_does_not_duplicate(self):
        self.assertEqual(self.upload(build()).status_code, 200)
        body = self.upload(build(), "/workouts/import/preview").json()
        self.assertEqual(body["workouts"][0]["replaces"], {"sets": 7, "pasted_sets": 0})
        self.assertEqual(body["new_exercises"], [])
        # A renamed file must not create a second copy either.
        self.assertEqual(self.upload(build(), name="Renamed.xlsx").status_code, 200)
        [day] = self.days()
        self.assertEqual(len(day["sets"]), 7)
        self.assertEqual(day["volume"], {"lb": 4610})
        self.assertEqual(day["sets"][0]["program"], "Renamed")

    def test_breakdown_is_saved(self):
        def edit(book):
            book.active["I10"] = "4 + 3"
        self.upload(build(edit))
        bench = next(s for s in self.days()[0]["sets"] if s["exercise"] == "Flat Bench")
        self.assertEqual(
            (bench["myo_raw"], bench["reps"], bench["full_reps"], bench["rest_pause_reps"], bench["partial_reps"]),
            ("4 + 3", 7, 4, 3, 0),
        )

    def test_other_dates_are_left_alone(self):
        self.upload(build())
        self.upload(build(day="2020.01.12"))
        self.assertEqual(len(self.days()), 2)

    def test_errors_save_nothing(self):
        self.assertEqual(self.upload(build(day="soon")).status_code, 422)
        self.assertEqual(self.upload(b"nope").status_code, 400)
        self.assertEqual(self.days(), [])

    def test_sheet_replaces_pasted_lifts_and_keeps_walks(self):
        self.client.post("/workouts", json={"text": "WORKOUT 2020-01-05\nlift | Bench | 100 lb | 5\nwalk | pad | 5 min"})
        self.upload(build())
        [day] = self.days()
        self.assertEqual((len(day["sets"]), len(day["activities"])), (7, 1))

    def test_paste_cannot_double_count_sheet_lifts(self):
        self.upload(build())
        paste = {"text": "WORKOUT 2020-01-05\nlift | Bench | 100 lb | 5"}
        self.assertTrue(self.client.post("/workouts/preview", json=paste).json()["errors"])
        self.assertEqual(self.client.post("/workouts", json=paste).status_code, 422)
        walk = {"text": "WORKOUT 2020-01-05\nwalk | pad | 5 min"}
        self.assertEqual(self.client.post("/workouts", json=walk).status_code, 200)
        self.assertEqual(len(self.days()[0]["sets"]), 7)

    def exercises(self):
        return {e["name"]: e for e in self.client.get("/workouts/exercises").json()["exercises"]}

    def link(self, name, same_as):
        return self.client.post("/workouts/exercises/link", json={"name": name, "same_as": same_as})

    def test_unique_names_ignore_case_and_spacing(self):
        self.upload(build())
        def edit(book):
            book.active["A10"] = "flat   BENCH"
        self.upload(build(edit, day="2020.01.12"))
        found = self.exercises()
        self.assertEqual(len(found), 5)
        self.assertEqual((found["flat BENCH"]["sets"], found["flat BENCH"]["last_done"]), (4, "2020-01-12"))

    def past(self, name):
        return self.client.get("/workouts/exercises/history", params={"name": name})

    def test_exercise_history_newest_first_with_best(self):
        self.upload(build())
        def edit(book):
            book.active["A10"] = "flat   BENCH"
            book.active["F10"] = "95"
            book.active["G10"] = 210
        self.upload(build(edit, day="2020.01.12"))
        body = self.past("Flat Bench").json()
        self.assertEqual([d["date"] for d in body["days"]], ["2020-01-12", "2020-01-05"])
        self.assertEqual([(s["weight"], s["reps"]) for s in body["days"][0]["sets"]], [(210, 7), (200, 6)])
        self.assertEqual(body["days"][0]["sessions"], ["UPPER A"])
        best = body["best"]
        self.assertEqual((best["weight"], best["per_side"], best["reps"], best["date"]), (230, 105, 7, "2020-01-05"))

    def test_history_includes_linked_names_either_way(self):
        self.upload(build())
        self.link("Leg Extensions", "Flat Bench")
        for name in ("Flat Bench", "leg extensions"):
            with self.subTest(name=name):
                sets = self.past(name).json()["days"][0]["sets"]
                self.assertEqual({s["exercise"] for s in sets}, {"Flat Bench", "Leg Extensions"})
                self.assertEqual(len(sets), 3)

    def test_best_without_weights_is_most_reps(self):
        self.upload(build())
        best = self.past("Close Grip Pulls").json()["best"]
        self.assertEqual((best["weight"], best["reps"]), (None, 3))

    def test_history_of_unknown_exercise(self):
        self.assertEqual(self.past("Nothing").status_code, 404)

    def test_link_and_unlink(self):
        self.upload(build())
        self.assertEqual(self.link("Leg Extensions", "Flat Bench").status_code, 200)
        self.assertEqual(self.exercises()["Flat Bench"]["sets"], 3)
        # Moving the target carries earlier links with it.
        self.link("Flat Bench", "Bodyweight Squats")
        self.assertEqual(self.exercises()["Bodyweight Squats"]["sets"], 4)
        self.assertEqual(self.link("Bodyweight Squats", "Leg Extensions").status_code, 400)
        self.client.post("/workouts/exercises/unlink", json={"name": "Leg Extensions"})
        self.assertEqual(self.exercises()["Leg Extensions"]["sets"], 1)
        # What was recorded never changes.
        self.assertIn("Leg Extensions", {s["exercise"] for s in self.days()[0]["sets"]})


if __name__ == "__main__":
    unittest.main()
