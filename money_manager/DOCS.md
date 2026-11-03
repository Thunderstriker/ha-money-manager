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
- **Multiple accounts**: import statements from separate accounts, filter the dashboard,
  transaction list and export by account, or select **Unassigned** for transactions
  whose original file did not specify an account.
- **Account names**: on the **Accounts** page, save a friendly name (e.g. "Everyday" or
  "Savings") for any account in your imports. The name appears in account selectors
  and transaction rows, while the bank account identifier remains unchanged.

## Usage

1. Start the add-on and open its Web UI (sidebar panel, via Ingress).
2. Go to **Import / Export**, choose a CSV, XLSX or camt.053 XML export from your bank, and click **Import**.
   If the export does not identify your own account, enter its IBAN in **Account override**.
   This also lets you override an account identifier in the file; leave it empty to use the file's account.
   Import each account's export separately. The account identifier is normalized (spaces removed,
   uppercase), and is part of the duplicate-detection key. To avoid duplicates on re-import,
   use the same override each time for account-less files.
3. Go to **Categories & Rules** to review/add categories and matching rules. Rules you add are applied to future imports automatically; use **Apply rules to uncategorized** (Transactions tab) to apply them retroactively.
4. Check the **Dashboard** tab for charts and totals.
5. Use the **Account** selector on the dashboard or transactions page to see one account,
   all accounts, or unassigned transactions. Click an account in the transaction list
   to reassign it (or clear the value). Export has its own account selector.
6. On the **Accounts** page, type a display name for each account and click **Save**.
   Clear the name and save to return to showing just the account identifier.

Existing transactions are kept as-is when upgrading; those without an account appear
under **Unassigned**. Cross-account transfers are currently counted on both sides
when viewing all accounts; categorize them as transfers if appropriate.
Display names are stored in the same SQLite database as your transactions; CSV export
retains the original account identifiers, not the friendly names.

## Configuration

| Option      | Description                                   |
|-------------|------------------------------------------------|
| `log_level` | Add-on log verbosity.                          |
| `currency`  | Default currency label shown in the dashboard. |

## Data storage

All data (SQLite database) is stored under the add-on's persistent `/data` directory, so it survives add-on restarts/updates. Use **Export** regularly, or back up your Home Assistant instance, to keep a copy of your data.

## Supported CSV column headers (auto-detected)

date, amount, debit/credit indicator, description, counterparty name, IBAN/account number — in English or Dutch (datum, bedrag, af bij, omschrijving, naam tegenpartij, rekeningnummer, ...). If your bank uses different headers, open an issue or rename the columns before importing.
