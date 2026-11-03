"""Money Manager - Flask backend.

Provides an ingress-friendly web UI + JSON API to import, categorize, export
and visualize online banking transactions.
"""
import csv
import io
import os

from flask import Flask, jsonify, request, send_file, render_template, Response

import db
import importers
import categorize as cat_engine

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB upload limit

db.init_db()


def ingress_prefix():
    return request.headers.get("X-Ingress-Path", "")


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", ingress_path=ingress_prefix())


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@app.route("/api/categories", methods=["GET"])
def list_categories():
    conn = db.get_db()
    rows = conn.execute("SELECT * FROM categories ORDER BY type, name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/categories", methods=["POST"])
def create_category():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    ctype = data.get("type", "expense")
    color = data.get("color", "#7f8c8d")
    if not name:
        return jsonify({"error": "name is required"}), 400
    conn = db.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO categories(name, type, color) VALUES (?, ?, ?)",
            (name, ctype, color),
        )
        conn.commit()
        new_id = cur.lastrowid
    except Exception as exc:  # noqa: BLE001
        conn.close()
        return jsonify({"error": str(exc)}), 400
    conn.close()
    return jsonify({"id": new_id}), 201


@app.route("/api/categories/<int:category_id>", methods=["PUT"])
def update_category(category_id):
    data = request.get_json(force=True)
    conn = db.get_db()
    conn.execute(
        "UPDATE categories SET name = ?, type = ?, color = ? WHERE id = ?",
        (data.get("name"), data.get("type"), data.get("color"), category_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
def delete_category(category_id):
    conn = db.get_db()
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@app.route("/api/rules", methods=["GET"])
def list_rules():
    conn = db.get_db()
    rows = conn.execute(
        """SELECT rules.*, categories.name AS category_name
           FROM rules JOIN categories ON categories.id = rules.category_id
           ORDER BY priority ASC, rules.id ASC"""
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/rules", methods=["POST"])
def create_rule():
    data = request.get_json(force=True)
    conn = db.get_db()
    cur = conn.execute(
        "INSERT INTO rules(pattern, field, category_id, priority) VALUES (?, ?, ?, ?)",
        (
            data.get("pattern", "").strip(),
            data.get("field", "any"),
            data.get("category_id"),
            data.get("priority", 100),
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"id": new_id}), 201


@app.route("/api/rules/<int:rule_id>", methods=["PUT"])
def update_rule(rule_id):
    data = request.get_json(force=True)
    conn = db.get_db()
    conn.execute(
        "UPDATE rules SET pattern = ?, field = ?, category_id = ?, priority = ? WHERE id = ?",
        (
            data.get("pattern", "").strip(),
            data.get("field", "any"),
            data.get("category_id"),
            data.get("priority", 100),
            rule_id,
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/rules/<int:rule_id>", methods=["DELETE"])
def delete_rule(rule_id):
    conn = db.get_db()
    conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/rules/apply", methods=["POST"])
def apply_rules():
    """Re-run categorization rules. By default only on uncategorized transactions;
    pass {"all": true} to re-apply to every transaction."""
    data = request.get_json(silent=True) or {}
    apply_all = bool(data.get("all"))

    conn = db.get_db()
    rules = cat_engine.sorted_rules(
        conn.execute("SELECT * FROM rules").fetchall()
    )
    if apply_all:
        rows = conn.execute("SELECT * FROM transactions").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE category_id IS NULL"
        ).fetchall()

    updated = 0
    for row in rows:
        tx = dict(row)
        category_id = cat_engine.categorize(tx, rules)
        if category_id is not None:
            conn.execute(
                "UPDATE transactions SET category_id = ? WHERE id = ?",
                (category_id, tx["id"]),
            )
            updated += 1
    conn.commit()
    conn.close()
    return jsonify({"updated": updated})


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

@app.route("/api/accounts", methods=["GET"])
def list_accounts():
    """List known accounts (including saved names and accounts with no transactions)."""
    conn = db.get_db()
    rows = conn.execute(
        """SELECT accounts.account, accounts.name, COUNT(transactions.id) AS count
           FROM accounts LEFT JOIN transactions ON transactions.account = accounts.account
           GROUP BY accounts.account ORDER BY accounts.account"""
    ).fetchall()
    unassigned = conn.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE account = ''"
    ).fetchone()["count"]
    conn.close()
    result = [dict(r) for r in rows]
    if unassigned:
        result.insert(0, {"account": "", "name": "", "count": unassigned})
    return jsonify(result)


@app.route("/api/accounts/<account>", methods=["PUT"])
def rename_account(account):
    account = _normalize_account(account)
    data = request.get_json(silent=True)
    if not account or account == "__UNASSIGNED__" or not isinstance(data, dict):
        return jsonify({"error": "invalid account or request body"}), 400
    name = data.get("name")
    if not isinstance(name, str) or len(name.strip()) > 80:
        return jsonify({"error": "name must be a string of at most 80 characters"}), 400
    conn = db.get_db()
    cur = conn.execute("UPDATE accounts SET name = ? WHERE account = ?", (name.strip(), account))
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return jsonify({"error": "account not found"}), 404
    return jsonify({"ok": True})


def _normalize_account(value):
    return "".join(value.split()).upper()

def _build_filters(args):
    clauses = []
    params = []
    if args.get("from"):
        clauses.append("date >= ?")
        params.append(args["from"])
    if args.get("to"):
        clauses.append("date <= ?")
        params.append(args["to"])
    if args.get("category_id"):
        clauses.append("category_id = ?")
        params.append(args["category_id"])
    if args.get("uncategorized") == "1":
        clauses.append("category_id IS NULL")
    if args.get("account") == "__unassigned__":
        clauses.append("account = ''")
    elif args.get("account"):
        clauses.append("account = ?")
        params.append(args["account"])
    if args.get("search"):
        clauses.append("(description LIKE ? OR counterparty LIKE ?)")
        like = f"%{args['search']}%"
        params.extend([like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


@app.route("/api/transactions", methods=["GET"])
def list_transactions():
    where, params = _build_filters(request.args)
    limit = int(request.args.get("limit", 500))
    offset = int(request.args.get("offset", 0))

    conn = db.get_db()
    rows = conn.execute(
        f"""SELECT transactions.*, categories.name AS category_name, categories.color AS category_color
            FROM transactions
            LEFT JOIN categories ON categories.id = transactions.category_id
            {where}
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) AS c FROM transactions {where}", params
    ).fetchone()["c"]
    conn.close()
    return jsonify({"items": [dict(r) for r in rows], "total": total})


@app.route("/api/transactions/<int:tx_id>", methods=["PUT"])
def update_transaction(tx_id):
    data = request.get_json(force=True)
    if "account" in data:
        if not isinstance(data["account"], str):
            return jsonify({"error": "account must be a string"}), 400
        data["account"] = _normalize_account(data["account"])
    fields = []
    params = []
    for key in ("date", "amount", "description", "counterparty", "iban", "account", "category_id"):
        if key in data:
            fields.append(f"{key} = ?")
            params.append(data[key])
    if not fields:
        return jsonify({"error": "no fields to update"}), 400
    params.append(tx_id)
    conn = db.get_db()
    conn.execute(f"UPDATE transactions SET {', '.join(fields)} WHERE id = ?", params)
    if data.get("account"):
        conn.execute("INSERT OR IGNORE INTO accounts(account) VALUES (?)", (data["account"],))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/transactions/<int:tx_id>/rules", methods=["POST"])
def create_rule_from_transaction(tx_id):
    """Create a matching rule and categorize this transaction in one operation.

    Optionally categorize other *uncategorized* matches without changing any
    existing manual categories. Rules apply across accounts, as usual.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "a JSON object is required"}), 400
    pattern = data.get("pattern")
    field = data.get("field")
    category_id = data.get("category_id")
    priority = data.get("priority", 0)
    apply_existing = data.get("apply_existing", True)
    if not isinstance(pattern, str) or not pattern.strip():
        return jsonify({"error": "enter a non-empty pattern"}), 400
    pattern = pattern.strip()
    if field not in ("description", "counterparty", "iban", "any"):
        return jsonify({"error": "invalid match field"}), 400
    if (not isinstance(priority, int) or isinstance(priority, bool) or
            not isinstance(category_id, int) or isinstance(category_id, bool) or
            not isinstance(apply_existing, bool)):
        return jsonify({"error": "invalid category, priority, or apply_existing"}), 400

    conn = db.get_db()
    try:
        tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if tx is None:
            return jsonify({"error": "transaction not found"}), 404
        if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone():
            return jsonify({"error": "category not found"}), 400
        rule = {"pattern": pattern, "field": field, "category_id": category_id, "priority": priority}
        if cat_engine.categorize(dict(tx), [rule]) is None:
            return jsonify({"error": "pattern does not match the selected transaction"}), 400

        cur = conn.execute(
            "INSERT INTO rules(pattern, field, category_id, priority) VALUES (?, ?, ?, ?)",
            (pattern, field, category_id, priority),
        )
        conn.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (category_id, tx_id))
        matched = 0
        if apply_existing:
            for other in conn.execute(
                "SELECT * FROM transactions WHERE category_id IS NULL AND id != ?", (tx_id,)
            ).fetchall():
                if cat_engine.categorize(dict(other), [rule]) is not None:
                    conn.execute(
                        "UPDATE transactions SET category_id = ? WHERE id = ?",
                        (category_id, other["id"]),
                    )
                    matched += 1
        conn.commit()
        return jsonify({"id": cur.lastrowid, "updated": matched + 1}), 201
    finally:
        conn.close()


@app.route("/api/transactions/<int:tx_id>", methods=["DELETE"])
def delete_transaction(tx_id):
    conn = db.get_db()
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

@app.route("/api/import", methods=["POST"])
def import_file():
    if "file" not in request.files:
        return jsonify({"error": "no file provided"}), 400
    file = request.files["file"]
    account_override = request.form.get("account", "")
    if account_override and not account_override.strip():
        return jsonify({"error": "account must not be blank"}), 400
    account_override = _normalize_account(account_override)
    raw = file.read()
    try:
        parsed = importers.parse_file(raw, file.filename)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"could not parse file: {exc}"}), 400
    for tx in parsed:
        tx["account"] = account_override or _normalize_account(tx.get("account", ""))

    conn = db.get_db()
    rules = cat_engine.sorted_rules(conn.execute("SELECT * FROM rules").fetchall())

    inserted = 0
    duplicates = 0
    for tx in parsed:
        if tx["account"]:
            conn.execute("INSERT OR IGNORE INTO accounts(account) VALUES (?)", (tx["account"],))
        tx_hash = importers.compute_hash(tx)
        existing = conn.execute(
            "SELECT id FROM transactions WHERE import_hash = ?", (tx_hash,)
        ).fetchone()
        if existing:
            duplicates += 1
            continue
        category_id = cat_engine.categorize(tx, rules)
        conn.execute(
            """INSERT INTO transactions
               (date, amount, currency, description, counterparty, iban, account,
                category_id, import_hash, source_file, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx["date"], tx["amount"], tx.get("currency", "EUR"),
                tx.get("description", ""), tx.get("counterparty", ""),
                tx.get("iban", ""), tx.get("account", ""),
                category_id, tx_hash, file.filename, db.now_iso(),
            ),
        )
        inserted += 1
    conn.commit()
    conn.close()
    return jsonify({"inserted": inserted, "duplicates": duplicates, "total_parsed": len(parsed)})


@app.route("/api/export", methods=["GET"])
def export_csv():
    where, params = _build_filters(request.args)
    conn = db.get_db()
    rows = conn.execute(
        f"""SELECT transactions.date, transactions.amount, transactions.currency,
                   transactions.description, transactions.counterparty, transactions.iban,
                   transactions.account, categories.name AS category
            FROM transactions
            LEFT JOIN categories ON categories.id = transactions.category_id
            {where}
            ORDER BY date ASC""",
        params,
    ).fetchall()
    conn.close()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "amount", "currency", "description", "counterparty", "iban", "account", "category"])
    for r in rows:
        writer.writerow([r["date"], r["amount"], r["currency"], r["description"],
                          r["counterparty"], r["iban"], r["account"], r["category"] or ""])

    mem = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="moneymanager_export.csv",
    )


# ---------------------------------------------------------------------------
# Summary / visualization data
# ---------------------------------------------------------------------------

@app.route("/api/summary/monthly", methods=["GET"])
def summary_monthly():
    """Income/expense totals per month (YYYY-MM)."""
    where, params = _build_filters(request.args)
    conn = db.get_db()
    rows = conn.execute(
        f"""SELECT substr(date, 1, 7) AS month,
                  SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,
                  SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS expense
           FROM transactions
           {where}
           GROUP BY month
           ORDER BY month ASC""",
        params,
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/summary/categories", methods=["GET"])
def summary_categories():
    """Expense totals per category, optionally filtered by date range / month."""
    where, params = _build_filters(request.args)
    where_clause = f"{where} AND amount < 0" if where else "WHERE amount < 0"
    conn = db.get_db()
    rows = conn.execute(
        f"""SELECT COALESCE(categories.name, 'Uncategorized') AS category,
                   COALESCE(categories.color, '#7f8c8d') AS color,
                   SUM(-transactions.amount) AS total
            FROM transactions
            LEFT JOIN categories ON categories.id = transactions.category_id
            {where_clause}
            GROUP BY category, color
            ORDER BY total DESC""",
        params,
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/summary/totals", methods=["GET"])
def summary_totals():
    where, params = _build_filters(request.args)
    conn = db.get_db()
    row = conn.execute(
        f"""SELECT
                COUNT(*) AS count,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS expense
            FROM transactions
            {where}""",
        params,
    ).fetchone()
    uncategorized_where = f"{where} AND category_id IS NULL" if where else "WHERE category_id IS NULL"
    uncategorized = conn.execute(
        f"SELECT COUNT(*) AS c FROM transactions {uncategorized_where}", params
    ).fetchone()["c"]
    conn.close()
    data = dict(row)
    data["income"] = data["income"] or 0
    data["expense"] = data["expense"] or 0
    data["net"] = data["income"] - data["expense"]
    data["uncategorized"] = uncategorized
    return jsonify(data)


@app.route("/healthz")
def healthz():
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("MONEYMANAGER_INGRESS_PORT", "8099"))
    app.run(host="0.0.0.0", port=port, debug=True)
