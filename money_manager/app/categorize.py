"""Rule-based transaction categorization."""


def _field_values(tx, field):
    if field == "description":
        return [tx.get("description", "")]
    if field == "counterparty":
        return [tx.get("counterparty", "")]
    if field == "iban":
        return [tx.get("iban", ""), tx.get("account", "")]
    # "any"
    return [
        tx.get("description", ""),
        tx.get("counterparty", ""),
        tx.get("iban", ""),
        tx.get("account", ""),
    ]


def categorize(tx, rules):
    """rules: list of sqlite3.Row-like dicts with pattern, field, category_id, priority, direction,
    already sorted by priority ascending (lower = higher priority)."""
    for rule in rules:
        direction = rule["direction"]
        amount = tx.get("amount", 0)
        if (direction == "incoming" and amount <= 0 or
                direction == "outgoing" and amount >= 0):
            continue
        pattern = (rule["pattern"] or "").strip().lower()
        if not pattern:
            continue
        for value in _field_values(tx, rule["field"]):
            if pattern in (value or "").lower():
                return rule["category_id"]
    return None


def sorted_rules(rules):
    return sorted(rules, key=lambda r: r["priority"])
