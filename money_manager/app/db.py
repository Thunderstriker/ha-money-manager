"""SQLite persistence layer for Money Manager."""
import os
import sqlite3
import datetime

DATA_DIR = os.environ.get("MONEYMANAGER_DATA", "./data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "moneymanager.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK(type IN ('income','expense','transfer')) DEFAULT 'expense',
    color TEXT NOT NULL DEFAULT '#7f8c8d'
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    field TEXT NOT NULL CHECK(field IN ('description','counterparty','iban','any')) DEFAULT 'any',
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    priority INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    description TEXT NOT NULL DEFAULT '',
    counterparty TEXT NOT NULL DEFAULT '',
    iban TEXT NOT NULL DEFAULT '',
    account TEXT NOT NULL DEFAULT '',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    import_hash TEXT UNIQUE,
    source_file TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account TEXT PRIMARY KEY NOT NULL CHECK(account <> ''),
    name TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account);
"""

DEFAULT_CATEGORIES = [
    ("Salary", "income", "#2ecc71"),
    ("Other income", "income", "#27ae60"),
    ("Groceries", "expense", "#e67e22"),
    ("Housing & Rent", "expense", "#8e44ad"),
    ("Utilities", "expense", "#2980b9"),
    ("Insurance", "expense", "#16a085"),
    ("Transport", "expense", "#d35400"),
    ("Health", "expense", "#c0392b"),
    ("Shopping", "expense", "#f39c12"),
    ("Restaurants & Takeaway", "expense", "#e74c3c"),
    ("Subscriptions", "expense", "#9b59b6"),
    ("Savings & Transfers", "transfer", "#34495e"),
    ("Uncategorized", "expense", "#7f8c8d"),
]

DEFAULT_RULES = [
    # (pattern, field, category_name, priority)
    ("albert heijn", "any", "Groceries", 10),
    ("jumbo", "any", "Groceries", 10),
    ("lidl", "any", "Groceries", 10),
    ("aldi", "any", "Groceries", 10),
    ("plus supermarkt", "any", "Groceries", 10),
    ("netflix", "any", "Subscriptions", 10),
    ("spotify", "any", "Subscriptions", 10),
    ("disney", "any", "Subscriptions", 10),
    ("ns groep", "any", "Transport", 10),
    ("shell", "any", "Transport", 10),
    ("bp ", "any", "Transport", 10),
    ("salaris", "description", "Salary", 5),
    ("salary", "description", "Salary", 5),
    ("huur", "description", "Housing & Rent", 10),
    ("rent ", "description", "Housing & Rent", 10),
    ("vattenfall", "any", "Utilities", 10),
    ("eneco", "any", "Utilities", 10),
    ("waternet", "any", "Utilities", 10),
    ("zilveren kruis", "any", "Insurance", 10),
    ("cz zorgverzekering", "any", "Insurance", 10),
    ("apotheek", "any", "Health", 10),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        # Pick up accounts from databases created before account names existed.
        # Never change transaction rows or their import hashes during the upgrade.
        conn.execute(
            """INSERT OR IGNORE INTO accounts(account)
               SELECT DISTINCT account FROM transactions WHERE account <> ''"""
        )
        existing = conn.execute("SELECT COUNT(*) AS c FROM categories").fetchone()["c"]
        if existing == 0:
            conn.executemany(
                "INSERT INTO categories(name, type, color) VALUES (?, ?, ?)",
                DEFAULT_CATEGORIES,
            )
            conn.commit()
            cat_rows = conn.execute("SELECT id, name FROM categories").fetchall()
            name_to_id = {r["name"]: r["id"] for r in cat_rows}
            rule_rows = [
                (pattern, field, name_to_id[cat_name], priority)
                for (pattern, field, cat_name, priority) in DEFAULT_RULES
                if cat_name in name_to_id
            ]
            conn.executemany(
                "INSERT INTO rules(pattern, field, category_id, priority) VALUES (?, ?, ?, ?)",
                rule_rows,
            )
        conn.commit()
    finally:
        conn.close()


def now_iso():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
