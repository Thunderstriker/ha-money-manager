"""Category editing API regression tests."""
import os
import tempfile
import unittest

import db
import main


class CategoriesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmp.name, "money.db")
        db.init_db()
        self.client = main.app.test_client()
        self.category = next(c for c in self.client.get("/api/categories").get_json()
                             if c["name"] == "Groceries")
        self.url = f"/api/categories/{self.category['id']}"

    def tearDown(self):
        db.DB_PATH = self.previous_db_path
        self.tmp.cleanup()

    def saved_category(self):
        return next(c for c in self.client.get("/api/categories").get_json()
                    if c["id"] == self.category["id"])

    def test_edit_preserves_transactions_and_rules(self):
        conn = db.get_db()
        conn.execute(
            """INSERT INTO transactions(date, amount, category_id, created_at)
               VALUES ('2024-01-01', -10, ?, '2024-01-01T00:00:00Z')""",
            (self.category["id"],),
        )
        before_rules = [dict(r) for r in conn.execute("SELECT * FROM rules")]
        before_tx = dict(conn.execute("SELECT * FROM transactions").fetchone())
        conn.commit()
        conn.close()
        response = self.client.put(self.url, json={
            "name": "  Food & Drink  ", "type": "transfer", "color": "#123aBc",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.saved_category(), {
            "id": self.category["id"], "name": "Food & Drink", "type": "transfer", "color": "#123aBc",
        })
        conn = db.get_db()
        self.assertEqual([dict(r) for r in conn.execute("SELECT * FROM rules")], before_rules)
        self.assertEqual(dict(conn.execute("SELECT * FROM transactions").fetchone()), before_tx)
        conn.close()
        tx = self.client.get("/api/transactions").get_json()["items"][0]
        self.assertEqual(tx["category_name"], "Food & Drink")
        self.assertEqual(tx["category_color"], "#123aBc")
        summary = self.client.get("/api/summary/categories").get_json()[0]
        self.assertEqual(summary["category"], "Food & Drink")
        self.assertEqual(summary["color"], "#123aBc")
        self.assertEqual(summary["total"], 10)
        linked_rules = [r for r in self.client.get("/api/rules").get_json()
                        if r["category_id"] == self.category["id"]]
        self.assertTrue(linked_rules)
        self.assertTrue(all(r["category_name"] == "Food & Drink" for r in linked_rules))

    def test_partial_update_preserves_other_fields(self):
        self.assertEqual(self.client.put(self.url, json={"name": "Food"}).status_code, 200)
        expected = dict(self.category, name="Food")
        self.assertEqual(self.saved_category(), expected)
        self.assertEqual(self.client.put(self.url, json={}).status_code, 200)
        self.assertEqual(self.saved_category(), expected)

    def test_invalid_fields_leave_category_unchanged(self):
        for data in ({"name": ""}, {"name": "  "}, {"name": None}, {"name": 42},
                     {"type": "unknown"}, {"type": None}, {"type": []},
                     {"color": "red"}, {"color": "#xyzxyz"}, {"color": None},
                     {"color": "#123"}, {"color": 123}, {"name": "Salary"}):
            with self.subTest(data=data):
                response = self.client.put(self.url, json=data)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())
                self.assertEqual(self.saved_category(), self.category)
        # A failed duplicate update must not leave a database lock behind.
        self.assertEqual(self.client.put(self.url, json={"name": "Food"}).status_code, 200)

    def test_invalid_body_and_missing_category(self):
        for body in ([], "name", None):
            self.assertEqual(self.client.put(self.url, json=body).status_code, 400)
        self.assertEqual(self.client.put(self.url, data="{", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.put("/api/categories/999999", json={"name": "Food"}).status_code, 404)
        self.assertEqual(self.saved_category(), self.category)


if __name__ == "__main__":
    unittest.main()
