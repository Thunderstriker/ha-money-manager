"""Account-aware import, filtering and export regression tests."""
import io
import os
import tempfile
import unittest

import db
import main
import openpyxl


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self.tmp.name, "money.db")
        db.init_db()
        self.client = main.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def upload(self, csv_text, account=None):
        data = {"file": (io.BytesIO(csv_text.encode()), "statement.csv")}
        if account is not None:
            data["account"] = account
        return self.client.post("/api/import", data=data).get_json()

    def test_multiple_accounts_and_unassigned(self):
        csv_text = (
            "date,amount,description,account\n"
            "2024-01-03,-10,Food,BE11111111111111\n"
            "2024-01-03,-10,Food,BE22222222222222\n"
            "2024-02-01,100,Pay,BE11111111111111\n"
            "2024-02-02,-5,Coffee,\n"
        )
        self.assertEqual(self.upload(csv_text)["inserted"], 4)
        self.assertEqual(self.upload(csv_text)["duplicates"], 4)
        accounts = self.client.get("/api/accounts").get_json()
        self.assertEqual({a["account"]: a["count"] for a in accounts}, {
            "": 1, "BE11111111111111": 2, "BE22222222222222": 1,
        })
        a = "?account=BE11111111111111"
        self.assertEqual(self.client.get("/api/transactions" + a).get_json()["total"], 2)
        self.assertEqual(self.client.get("/api/summary/totals" + a).get_json()["net"], 90)
        monthly = self.client.get("/api/summary/monthly" + a).get_json()
        self.assertEqual([r["month"] for r in monthly], ["2024-01", "2024-02"])
        self.assertEqual(self.client.get("/api/summary/monthly" + a + "&from=2024-02-01")
                         .get_json()[0]["income"], 100)
        self.assertEqual(self.client.get("/api/summary/categories" + a).get_json()[0]["total"], 10)
        exported = self.client.get("/api/export" + a).data.decode("utf-8-sig")
        self.assertEqual(len(exported.splitlines()), 3)
        self.assertNotIn("BE22222222222222", exported)
        self.assertEqual(self.client.get("/api/transactions?account=__unassigned__")
                         .get_json()["total"], 1)

    def test_override_and_manual_assignment(self):
        csv_text = "date,amount,description\n2024-03-01,-7,Ticket\n"
        self.assertEqual(self.upload(csv_text, " be44 4444 4444 4444 ")["inserted"], 1)
        tx = self.client.get("/api/transactions").get_json()["items"][0]
        self.assertEqual(tx["account"], "BE44444444444444")
        self.assertEqual(self.upload(csv_text, "BE44444444444444")["duplicates"], 1)
        self.assertEqual(self.client.put(f"/api/transactions/{tx['id']}",
                                         json={"account": "BE55 5555"}).status_code, 200)
        self.assertEqual(self.client.get("/api/transactions?account=BE555555")
                         .get_json()["total"], 1)
        self.assertEqual(self.client.put(f"/api/transactions/{tx['id']}",
                                         json={"account": None}).status_code, 400)

    def test_argenta_xlsx_and_camt_accounts(self):
        wb = openpyxl.Workbook()
        wb.active.append(["Rekening", "Boekdatum", "Bedrag", "Beschrijving"])
        wb.active.append(["be11 1111 1111 1111", "2024-01-01", -12, "Shop"])
        wb.active.append(["be22 2222 2222 2222", "2024-01-01", -12, "Shop"])
        content = io.BytesIO()
        wb.save(content)
        result = self.client.post("/api/import", data={
            "file": (io.BytesIO(content.getvalue()), "argenta.xlsx")
        }).get_json()
        self.assertEqual(result["inserted"], 2)

        camt = b"""<Document><Stmt><Acct><Id><IBAN>BE33333333333333</IBAN></Id></Acct>
            <Ntry><Amt Ccy="EUR">5</Amt><CdtDbtInd>CRDT</CdtDbtInd>
            <BookgDt><Dt>2024-01-02</Dt></BookgDt></Ntry></Stmt></Document>"""
        result = self.client.post("/api/import", data={
            "file": (io.BytesIO(camt), "statement.xml")
        }).get_json()
        self.assertEqual(result["inserted"], 1)
        self.assertEqual({a["account"] for a in self.client.get("/api/accounts").get_json()}, {
            "BE11111111111111", "BE22222222222222", "BE33333333333333",
        })

    def test_account_names_survive_reimport_and_empty_account(self):
        csv_text = "date,amount,description,account\n2024-01-03,-10,Food,BE11111111111111\n"
        self.upload(csv_text)
        response = self.client.put("/api/accounts/BE11111111111111", json={"name": "  Everyday account  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.upload(csv_text)["duplicates"], 1)
        accounts = self.client.get("/api/accounts").get_json()
        self.assertEqual(accounts[0]["name"], "Everyday account")
        self.assertEqual(self.client.get("/api/transactions").get_json()["items"][0]["account"],
                         "BE11111111111111")
        self.assertIn("BE11111111111111", self.client.get("/api/export").data.decode("utf-8-sig"))
        self.assertEqual(self.client.put("/api/accounts/BE11111111111111", json={"name": ""}).status_code, 200)
        self.assertEqual(self.client.get("/api/accounts").get_json()[0]["name"], "")
        self.assertEqual(self.client.put("/api/accounts/__unassigned__", json={"name": "Other"}).status_code, 400)
        self.assertEqual(self.client.put("/api/accounts/BE999", json={"name": "Unknown"}).status_code, 404)
        self.assertEqual(self.client.put("/api/accounts/BE11111111111111", json={"name": 3}).status_code, 400)

    def test_upgrade_existing_database_and_keep_name_after_deleting_transactions(self):
        csv_text = "date,amount,description,account\n2024-01-03,-10,Food,BE11111111111111\n"
        self.upload(csv_text)
        conn = db.get_db()
        conn.execute("DROP TABLE accounts")  # Simulate the schema from the previous release.
        conn.commit()
        conn.close()
        db.init_db()
        self.assertEqual(self.client.get("/api/accounts").get_json()[0]["account"], "BE11111111111111")
        self.client.put("/api/accounts/BE11111111111111", json={"name": "Savings"})
        db.init_db()  # Subsequent app startups must not reset saved names.
        tx_id = self.client.get("/api/transactions").get_json()["items"][0]["id"]
        self.client.delete(f"/api/transactions/{tx_id}")
        self.assertEqual(self.client.get("/api/accounts").get_json()[0], {
            "account": "BE11111111111111", "name": "Savings", "count": 0,
        })


if __name__ == "__main__":
    unittest.main()
