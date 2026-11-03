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

    def test_rule_direction_on_import_and_existing_rule_edit(self):
        payload = {"pattern": "shared", "field": "description", "category_id": self.category,
                   "priority": 0, "direction": "incoming"}
        response = self.client.post("/api/rules", json=payload)
        self.assertEqual(response.status_code, 201)
        rule_id = response.get_json()["id"]
        self.import_csv("2024-01-01,10,Shared payment,BE111\n"
                        "2024-01-02,-10,Shared payment,BE222\n"
                        "2024-01-03,0,Shared payment,BE333\n")
        items = self.client.get("/api/transactions").get_json()["items"]
        self.assertEqual({tx["amount"]: tx["category_id"] for tx in items}, {
            10: self.category, -10: None, 0: None,
        })
        self.assertEqual(self.client.put(f"/api/rules/{rule_id}",
                                         json={"direction": "outgoing"}).status_code, 200)
        self.assertEqual(next(r for r in self.client.get("/api/rules").get_json()
                              if r["id"] == rule_id)["direction"], "outgoing")
        self.assertEqual(self.client.post("/api/rules/apply", json={"all": False})
                         .get_json()["updated"], 1)
        self.assertIsNone(next(tx for tx in self.client.get("/api/transactions").get_json()["items"]
                               if tx["amount"] == 0)["category_id"])
        self.import_csv("2024-02-01,20,Shared income,BE111\n"
                        "2024-02-02,-20,Shared expense,BE111\n")
        recent = {tx["amount"]: tx["category_id"] for tx in
                  self.client.get("/api/transactions").get_json()["items"]}
        self.assertIsNone(recent[20])
        self.assertEqual(recent[-20], self.category)
        self.assertEqual(self.client.post("/api/rules", json={**payload, "direction": "sideways"})
                         .status_code, 400)
        self.assertEqual(self.client.put(f"/api/rules/{rule_id}", json={"direction": "sideways"})
                         .status_code, 400)
        bp = next(r for r in self.client.get("/api/rules").get_json() if r["pattern"] == "bp ")
        self.assertEqual(self.client.put(f"/api/rules/{bp['id']}",
                                         json={"direction": "outgoing"}).status_code, 200)
        self.assertEqual(next(r for r in self.client.get("/api/rules").get_json()
                              if r["id"] == bp["id"])["pattern"], "bp ")

    def test_transaction_rule_direction_and_targeted_apply(self):
        self.import_csv("2024-01-01,15,Shared transfer,BE111\n"
                        "2024-01-02,-15,Shared transfer,BE222\n"
                        "2024-01-03,0,Shared transfer,BE333\n")
        tx = next(tx for tx in self.client.get("/api/transactions").get_json()["items"]
                  if tx["amount"] == 15)
        url = f"/api/transactions/{tx['id']}/rules"
        payload = {"pattern": "Shared", "field": "description", "category_id": self.category,
                   "direction": "incoming", "apply_existing": True}
        self.assertEqual(self.client.post(url, json={**payload, "direction": "outgoing"})
                         .status_code, 400)
        self.assertEqual(self.client.post(url, json=payload).get_json()["updated"], 1)
        rows = self.client.get("/api/transactions").get_json()["items"]
        self.assertEqual({row["amount"]: row["category_id"] for row in rows}, {
            15: self.category, -15: None, 0: None,
        })
        self.assertEqual(self.client.get("/api/rules").get_json()[0]["direction"], "incoming")

    def test_upgrade_rules_without_direction_keeps_prior_rules(self):
        conn = db.get_db()
        conn.execute("DROP TABLE rules")
        conn.execute("""CREATE TABLE rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT, pattern TEXT NOT NULL, field TEXT NOT NULL,
            category_id INTEGER NOT NULL, priority INTEGER NOT NULL DEFAULT 100)""")
        conn.execute("INSERT INTO rules(pattern, field, category_id, priority) VALUES (?, ?, ?, ?)",
                     ("legacy", "description", self.category, 9))
        conn.commit()
        conn.close()
        db.init_db()
        db.init_db()
        rules = self.client.get("/api/rules").get_json()
        self.assertEqual(len(rules), 1)
        self.assertEqual((rules[0]["pattern"], rules[0]["direction"], rules[0]["priority"]),
                         ("legacy", "any", 9))
        self.import_csv("2024-01-01,-10,Legacy shop,BE111\n"
                        "2024-01-02,10,Legacy refund,BE111\n")
        self.assertTrue(all(tx["category_id"] == self.category for tx in
                            self.client.get("/api/transactions").get_json()["items"]))


if __name__ == "__main__":
    unittest.main()
