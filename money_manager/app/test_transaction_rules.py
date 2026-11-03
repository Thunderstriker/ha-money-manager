"""Creating a categorization rule directly from a transaction."""
import io
import os
import tempfile
import unittest

import db
import main


class TransactionRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self.tmp.name, "money.db")
        db.init_db()
        self.client = main.app.test_client()
        self.category = next(
            row["id"] for row in self.client.get("/api/categories").get_json()
            if row["name"] == "Shopping"
        )
        self.other_category = next(
            row["id"] for row in self.client.get("/api/categories").get_json()
            if row["name"] == "Health"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def import_csv(self, rows):
        response = self.client.post("/api/import", data={
            "file": (io.BytesIO(("date,amount,description,account\n" + rows).encode()), "bank.csv")
        })
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_create_rule_categorizes_selected_and_only_uncategorized_matches(self):
        self.import_csv(
            "2024-01-01,-10,Acme Store,BE111\n"
            "2024-01-02,-20,Acme Online,BE222\n"
            "2024-01-03,-30,Acme Other,BE111\n"
            "2024-01-04,-40,Another Store,BE222\n"
        )
        items = self.client.get("/api/transactions").get_json()["items"]
        ids = {tx["description"]: tx["id"] for tx in items}
        self.client.put(f"/api/transactions/{ids['Acme Store']}",
                        json={"category_id": self.other_category})
        self.client.put(f"/api/transactions/{ids['Acme Other']}",
                        json={"category_id": self.other_category})
        response = self.client.post(f"/api/transactions/{ids['Acme Store']}/rules", json={
            "pattern": "acme", "field": "description", "category_id": self.category,
            "priority": 0, "apply_existing": True,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["updated"], 2)
        categories = {
            tx["description"]: tx["category_id"]
            for tx in self.client.get("/api/transactions").get_json()["items"]
        }
        self.assertEqual(categories, {
            "Acme Store": self.category, "Acme Online": self.category,
            "Acme Other": self.other_category, "Another Store": None,
        })
        self.assertEqual(self.import_csv("2024-01-05,-5,Acme Shop,BE222\n")["inserted"], 1)
        self.assertEqual(self.client.get("/api/transactions").get_json()["items"][0]["category_id"],
                         self.category)

    def test_optional_apply_and_input_validation(self):
        self.import_csv("2024-01-01,-10,Unique Shop,BE111\n2024-01-02,-20,Unique Market,BE222\n")
        tx = next(tx for tx in self.client.get("/api/transactions").get_json()["items"]
                  if tx["description"] == "Unique Shop")
        url = f"/api/transactions/{tx['id']}/rules"
        payload = {"pattern": "Unique", "field": "description", "category_id": self.category,
                   "priority": 0, "apply_existing": False}
        for invalid in ({**payload, "pattern": "not present"},
                        {**payload, "category_id": 999999},
                        {**payload, "field": "some_field"},
                        {**payload, "priority": True},
                        {**payload, "pattern": "   "}):
            self.assertEqual(self.client.post(url, json=invalid).status_code, 400)
        self.assertEqual(len(self.client.get("/api/rules").get_json()), len(db.DEFAULT_RULES))
        self.assertEqual(self.client.post(url, json=payload).status_code, 201)
        items = self.client.get("/api/transactions").get_json()["items"]
        self.assertEqual({tx["description"]: tx["category_id"] for tx in items}, {
            "Unique Shop": self.category, "Unique Market": None,
        })
        self.assertEqual(self.client.post("/api/transactions/999999/rules", json=payload).status_code,
                         404)


if __name__ == "__main__":
    unittest.main()
