# Home Assistant Add-on: Money Manager

Import, categorize and visualize your online banking transactions, directly from Home Assistant's sidebar.

## Features

- **Import** bank exports:
  - Generic CSV exports (auto-detects delimiter and common column names in English and Dutch — ING, ABN AMRO, Rabobank, bunq, SNS, Argenta, etc.)
  - Excel (`.xlsx`) exports, as used by banks that don't offer CSV (e.g. **Argenta**, which only exports `.xlsx`).
  - ISO 20022 `camt.053` XML bank statements (used by most EU banks)
  - Automatic de-duplication, so importing the same file (or an overlapping period) twice is safe.
- **Categorize** transactions:
  - Define your own categories (income / expense / transfer) with colors.
  - Define keyword-based rules (e.g. "albert heijn" → Groceries) that are automatically applied on import.
  - Re-apply rules at any time, to uncategorized transactions only or to everything.
  - Manually override the category of any transaction from the Transactions tab.
- **Visualize**:
  - Monthly income vs. expenses bar chart.
  - Expense breakdown by category (doughnut chart).
  - Totals cards: income, expenses, net, and uncategorized count.
- **Export** the currently filtered transactions back out to CSV.

## Usage

1. Start the add-on and open its Web UI (sidebar panel, via Ingress).
2. Go to **Import / Export**, choose a CSV or camt.053 XML export from your bank, and click **Import**.
3. Go to **Categories & Rules** to review/add categories and matching rules. Rules you add are applied to future imports automatically; use **Apply rules to uncategorized** (Transactions tab) to apply them retroactively.
4. Check the **Dashboard** tab for charts and totals.

## Configuration

| Option      | Description                                   |
|-------------|------------------------------------------------|
| `log_level` | Add-on log verbosity.                          |
| `currency`  | Default currency label shown in the dashboard. |

## Data storage

All data (SQLite database) is stored under the add-on's persistent `/data` directory, so it survives add-on restarts/updates. Use **Export** regularly, or back up your Home Assistant instance, to keep a copy of your data.

## Supported CSV column headers (auto-detected)

date, amount, debit/credit indicator, description, counterparty name, IBAN/account number — in English or Dutch (datum, bedrag, af bij, omschrijving, naam tegenpartij, rekeningnummer, ...). If your bank uses different headers, open an issue or rename the columns before importing.
