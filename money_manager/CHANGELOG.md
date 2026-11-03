# Changelog

## 0.5.1

- Choose Include only or Exclude for the dashboard category filter, keeping Exclude Savings & Transfers as the default.
- Select the current year and month when opening the dashboard, even when that period has no transactions.
- Remove the dashboard Refresh button; filter changes automatically update totals, charts, and transaction lists.

## 0.5.0

- Edit category names, types, and colors from Categories & Rules without losing linked transactions or rules.
- Validate category edits and show errors for invalid values or duplicate names.
- Add incoming transaction and expense lists to the dashboard, using the same account, year/month, and category exclusion filters as the totals and charts.
- Show all matching transactions newest first in scrollable lists, with empty-state messages when no transactions match.

## 0.4.0

- Replace dashboard From/To date filters with year and optional month selectors.
- Add a category exclusion filter for all dashboard totals and charts, defaulting to Savings & Transfers.
- Keep all-history and full-year views available, and preserve the existing CSV export date filters.

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
