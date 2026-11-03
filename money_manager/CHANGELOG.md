# Changelog

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
