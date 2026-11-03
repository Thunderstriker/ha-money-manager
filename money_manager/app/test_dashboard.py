"""Dashboard period and category exclusion regression tests."""
import os
import tempfile
import unittest

import db
import main


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmp.name, "money.db")
        db.init_db()
        self.client = main.app.test_client()
        conn = db.get_db()
        categories = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories")}
        self.savings_id = categories["Savings & Transfers"]
        self.groceries_id = categories["Groceries"]
        rows = [
            ("2023-12-31", -10, "BE111", self.groceries_id),
            ("2024-01-01", 1000, "BE111", categories["Salary"]),
            ("2024-02-01", -20, "BE111", self.groceries_id),
            ("2024-02-29", -30, "BE111", None),
            ("2024-02-15", -200, "BE111", self.savings_id),
            ("2024-02-15", 200, "BE222", self.savings_id),
            ("2024-02-28", -40, "", self.groceries_id),
            ("2024-03-01", -50, "BE111", self.groceries_id),
            ("2024-12-31", -60, "BE111", self.groceries_id),
            ("2025-01-01", 2000, "BE111", categories["Salary"]),
        ]
        conn.executemany(
            """INSERT INTO transactions(date, amount, account, category_id, created_at)
               VALUES (?, ?, ?, ?, '2026-01-01T00:00:00Z')""", rows,
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_PATH = self.previous_db_path
        self.tmp.cleanup()

    def summary(self, endpoint, **filters):
        response = self.client.get(f"/api/summary/{endpoint}", query_string=filters)
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_available_years_are_unique_descending_and_unfiltered(self):
        self.assertEqual(self.summary("years"), ["2025", "2024", "2023"])
        self.assertEqual(self.summary("years", account="BE222", exclude_category_id=self.savings_id),
                         ["2025", "2024", "2023"])

    def test_whole_year_includes_first_and_last_day(self):
        totals = self.summary("totals", year="2024")
        self.assertEqual(totals["count"], 8)
        self.assertEqual(totals["income"], 1200)
        self.assertEqual(totals["expense"], 400)
        self.assertEqual([r["month"] for r in self.summary("monthly", year="2024")],
                         ["2024-01", "2024-02", "2024-03", "2024-12"])

    def test_month_and_exclusion_apply_to_all_summaries(self):
        filters = {"year": "2024", "month": "02", "exclude_category_id": self.savings_id}
        totals = self.summary("totals", **filters)
        self.assertEqual(totals, {
            "count": 3, "income": 0, "expense": 90, "net": -90, "uncategorized": 1,
        })
        self.assertEqual(self.summary("monthly", **filters), [
            {"month": "2024-02", "income": 0, "expense": 90},
        ])
        self.assertEqual({r["category"]: r["total"] for r in self.summary("categories", **filters)},
                         {"Groceries": 60, "Uncategorized": 30})
        self.assertEqual(self.summary("totals", **dict(filters, month="2")), totals)

    def test_exclusion_combines_with_account_and_can_be_cleared(self):
        filters = {"year": "2024", "month": "02", "account": "BE111"}
        self.assertEqual(self.summary("totals", **filters)["expense"], 250)
        excluded = self.summary("totals", **dict(filters, exclude_category_id=self.savings_id))
        self.assertEqual(excluded["expense"], 50)
        self.assertEqual(excluded["uncategorized"], 1)
        self.assertEqual(self.summary("totals", **dict(filters, exclude_category_id=""))["expense"], 250)
        self.assertEqual(self.summary("totals", year="2024", month="02", account="__unassigned__",
                                      exclude_category_id=self.savings_id)["expense"], 40)

    def test_any_category_can_be_excluded_without_losing_uncategorized(self):
        filters = {"year": "2024", "month": "02", "exclude_category_id": self.groceries_id}
        self.assertEqual(self.summary("totals", **filters)["expense"], 230)
        self.assertEqual(self.summary("totals", **filters)["uncategorized"], 1)
        self.assertNotIn("Groceries", [r["category"] for r in self.summary("categories", **filters)])

    def test_all_years_and_empty_period(self):
        self.assertEqual(self.summary("totals")["count"], 10)
        # A month is only meaningful together with a year, as in the UI.
        self.assertEqual(self.summary("totals", month="02")["count"], 10)
        self.assertEqual(self.summary("totals", year="2024", month="04"), {
            "count": 0, "income": 0, "expense": 0, "net": 0, "uncategorized": 0,
        })
        self.assertEqual(self.summary("monthly", year="2024", month="04"), [])
        self.assertEqual(self.summary("categories", year="2024", month="04"), [])
        conn = db.get_db()
        conn.execute("DELETE FROM transactions")
        conn.commit()
        conn.close()
        self.assertEqual(self.summary("years"), [])

    def test_dashboard_controls_and_export_date_filters(self):
        page = self.client.get("/", headers={"X-Ingress-Path": "/ingress/money"}).get_data(as_text=True)
        for control in ("dash-year", "dash-month", "dash-exclude-category", "export-from", "export-to"):
            self.assertIn(f'id="{control}"', page)
        self.assertNotIn('id="dash-from"', page)
        self.assertNotIn('id="dash-to"', page)
        self.assertIn('/ingress/money/static/js/app.js', page)
        exported = self.client.get("/api/export?from=2024-02-29&to=2024-03-01").data.decode("utf-8-sig")
        self.assertEqual(len(exported.splitlines()), 3)
        self.assertIn("2024-02-29", exported)
        self.assertIn("2024-03-01", exported)


if __name__ == "__main__":
    unittest.main()
