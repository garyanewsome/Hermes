"""Completion history. Needs a throwaway Postgres, never the real one:

    PLANNER_TEST_DB_URL=postgresql://... python -m unittest discover tests
"""

import os
import unittest

TEST_DB_URL = os.environ.get("PLANNER_TEST_DB_URL")
if TEST_DB_URL:
    os.environ["PLANNER_DB_URL"] = TEST_DB_URL


@unittest.skipUnless(TEST_DB_URL, "PLANNER_TEST_DB_URL not set")
class TodoCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import planner_db

        # Guards against app.config having been imported with the real URL.
        assert planner_db.PLANNER_DB_URL == TEST_DB_URL
        cls.db = planner_db
        cls.db.init_planner_db()
        cls.db.init_planner_db()  # migrations must be safe to repeat

    def setUp(self):
        self.list_id = self.db.create_todo_list("completion test")["id"]
        self.item_ids = []

    def tearDown(self):
        self.db.delete_todo_list(self.list_id)
        with self.db._connect() as conn:
            conn.execute("DELETE FROM todo_completions WHERE item_id = ANY(%s)", (self.item_ids,))

    def item(self, **kwargs):
        item_id = self.db.create_todo_item(self.list_id, "water plants", **kwargs)["id"]
        self.item_ids.append(item_id)
        return item_id

    def rows(self, item_id):
        with self.db._connect() as conn:
            return conn.execute(
                "SELECT * FROM todo_completions WHERE item_id = %s ORDER BY id", (item_id,)
            ).fetchall()

    def test_one_off_records_text_and_list(self):
        item_id = self.item()
        self.assertTrue(self.db.update_todo_item(item_id, done=True)["done"])
        [row] = self.rows(item_id)
        self.assertEqual((row["item_text"], row["list_name"]), ("water plants", "completion test"))

    def test_repeating_done_does_not_duplicate(self):
        item_id = self.item()
        self.db.update_todo_item(item_id, done=True)
        self.db.update_todo_item(item_id, done=True)
        self.assertEqual(len(self.rows(item_id)), 1)

    def test_uncheck_removes_the_row(self):
        item_id = self.item()
        self.db.update_todo_item(item_id, done=True)
        self.db.update_todo_item(item_id, done=False)
        self.assertEqual(self.rows(item_id), [])

    def test_uncheck_of_open_item_keeps_history(self):
        item_id = self.item(recurrence_days=3)
        self.db.update_todo_item(item_id, done=True)
        self.db.update_todo_item(item_id, done=False)
        self.assertEqual(len(self.rows(item_id)), 1)

    def test_recurring_by_days_records_every_check_off(self):
        item_id = self.item(recurrence_days=3)
        self.assertFalse(self.db.update_todo_item(item_id, done=True)["done"])
        self.db.update_todo_item(item_id, done=True)
        self.assertEqual(len(self.rows(item_id)), 2)

    def test_recurring_by_weekday_records(self):
        item_id = self.item(recurrence_weekdays="1,3,5")
        self.db.update_todo_item(item_id, done=True)
        self.assertEqual(len(self.rows(item_id)), 1)

    def test_skip_and_edits_record_nothing(self):
        item_id = self.item(recurrence_days=3)
        self.db.skip_todo_item(item_id)
        self.db.update_todo_item(item_id, text="water the plants")
        self.assertEqual(self.rows(item_id), [])

    def test_history_survives_delete(self):
        item_id = self.item()
        self.db.update_todo_item(item_id, done=True)
        self.db.delete_todo_item(item_id)
        self.assertEqual(len(self.rows(item_id)), 1)


if __name__ == "__main__":
    unittest.main()
