# Changelog

## 0.3.0

- Match rules by transaction direction: Any, Incoming (positive), or Outgoing (negative).
- Choose direction when creating a rule manually or from a transaction; edit existing rules in Categories & Rules.
- Existing rules migrate to Any direction without changing their previous behavior.

## 0.2.2

- Add a Create rule dialog to every transaction, with suggested match text and its category preselected.
- Optionally categorize other matching uncategorized transactions immediately, without overwriting existing manual categories.

## 0.2.1

- Add an Accounts page to give each bank account a friendly display name.
- Display names appear in account filters and the transaction list; identifiers and transaction data stay unchanged.
- Preserve names through imports and app restarts, including accounts with no transactions.

## 0.2.0

- Track transactions from multiple bank accounts separately; filter the dashboard, transaction list, and CSV export by account.
- Import account identifiers from bank files, or provide an account override when importing files without one.
- Show unassigned transactions and allow account reassignment from the transaction list.

## 0.1.1

- Fix add-on build failure: `ghcr.io/hassio-addons/base-python:17.0.1` no longer exists; bumped base image to `20.0.0`.

## 0.1.0

- Initial release.
- Import CSV (auto-detected EN/NL bank headers) and ISO 20022 camt.053 XML.
- Rule-based auto-categorization with editable categories and rules.
- Dashboard with monthly income/expense and category breakdown charts.
- CSV export of filtered transactions.
