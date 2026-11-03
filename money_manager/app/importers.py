"""Parsers that turn raw bank export files into a list of normalized transaction dicts.

Each normalized transaction dict has keys:
    date (YYYY-MM-DD str), amount (float, +income/-expense), currency (str),
    description (str), counterparty (str), iban (str), account (str)
"""
import csv
import hashlib
import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime

# Candidate header names (lowercased) mapped to normalized fields.
# Covers generic English headers plus common Dutch bank export headers
# (ING, Rabobank, ABN AMRO, SNS, bunq, ...).
HEADER_MAP = {
    "date": ["date", "datum", "transaction date", "boekdatum", "transactiedatum", "valuedate", "value date"],
    "amount": ["amount", "bedrag", "bedrag (eur)", "value", "transaction amount", "amount (eur)"],
    "debit_credit": ["af bij", "af/bij", "debit/credit", "cd", "mutatiesoort", "type"],
    "description": [
        "description", "omschrijving", "omschrijving-1", "mededelingen", "mededeling", "notes",
        "name / description", "transactieomschrijving", "beschrijving",
        "naam / omschrijving", "naam/omschrijving", "vrije mededeling",
    ],
    "counterparty": [
        "counterparty", "naam tegenpartij", "naam", "tegenrekening naam", "name",
        "tegenpartij",
    ],
    "iban": [
        "iban", "account number", "rekeningnummer", "tegenrekening", "tegenrekening iban",
        "accountnumber", "counterparty iban", "rekening tegenpartij",
    ],
    "account": ["account", "rekening", "eigen rekening", "iban account"],
    "currency": ["currency", "munt", "valuta"],
    "reference": ["referentie", "reference"],
}

DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y%m%d", "%d.%m.%Y", "%m/%d/%Y"]


def _normalize_header(h):
    return re.sub(r"\s+", " ", h.strip().lower())


def _match_field(header):
    header = _normalize_header(header)
    for field, candidates in HEADER_MAP.items():
        if header in candidates:
            return field
    return None


def _parse_date(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    value = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    # Fallback: try ISO-like substring YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return value


def _parse_amount(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip().replace("€", "").replace(" ", "")
    if value == "":
        return 0.0
    # European formatting: 1.234,56 -> 1234.56
    if re.match(r"^-?\d{1,3}(\.\d{3})*,\d+$", value):
        value = value.replace(".", "").replace(",", ".")
    elif "," in value and "." not in value:
        value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return 0.0


def _cell_str(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _rows_to_transactions(header, rows):
    """Shared logic: turn a header row + data rows (lists of raw cell values,
    which may be str/float/date depending on source) into normalized transactions."""
    field_idx = {}
    for idx, h in enumerate(header):
        field = _match_field(_cell_str(h))
        if field and field not in field_idx:
            field_idx[field] = idx

    transactions = []
    for row in rows:
        if len(row) < len(header):
            row = list(row) + [""] * (len(header) - len(row))

        def get_raw(field):
            idx = field_idx.get(field)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        def get(field, default=""):
            raw = get_raw(field)
            return _cell_str(raw) if raw is not None else default

        date_raw = get_raw("date")
        if date_raw is None or _cell_str(date_raw) == "":
            continue
        amount = _parse_amount(get_raw("amount"))
        dc = get("debit_credit").strip().lower()
        if dc in ("af", "debit", "d", "-"):
            amount = -abs(amount)
        elif dc in ("bij", "credit", "c", "+"):
            amount = abs(amount)

        transactions.append({
            "date": _parse_date(date_raw),
            "amount": amount,
            "currency": get("currency", "EUR") or "EUR",
            "description": get("description").strip(),
            "counterparty": get("counterparty").strip(),
            "iban": get("iban").strip().replace(" ", ""),
            "account": get("account").strip().replace(" ", ""),
        })
    return transactions


def parse_csv(raw_bytes, filename="import.csv"):
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw_bytes.decode("utf-8", errors="replace")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        class _Default(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\r\n"
            quoting = csv.QUOTE_MINIMAL
        dialect = _Default

    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return []

    return _rows_to_transactions(rows[0], rows[1:])


def parse_xlsx(raw_bytes, filename="import.xlsx"):
    """Parse an Excel export (e.g. Argenta, which only offers .xlsx downloads)."""
    import openpyxl  # imported lazily so CSV-only setups don't need the dependency

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    sheet = wb.worksheets[0]
    rows = [list(r) for r in sheet.iter_rows(values_only=True)]
    rows = [r for r in rows if any(c not in (None, "") for c in r)]
    if not rows:
        return []
    return _rows_to_transactions(rows[0], rows[1:])



def _strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find(elem, path):
    """Find a child by path of local (namespace-stripped) tag names, e.g. 'Amt'."""
    parts = path.split("/")
    current = [elem]
    for part in parts:
        nxt = []
        for c in current:
            for child in c:
                if _strip_ns(child.tag) == part:
                    nxt.append(child)
        current = nxt
        if not current:
            return None
    return current[0] if current else None


def parse_camt053(raw_bytes, filename="import.xml"):
    """Parse an ISO 20022 camt.053 bank statement XML (common EU bank export)."""
    root = ET.fromstring(raw_bytes)
    transactions = []

    stmts = []
    for elem in root.iter():
        if _strip_ns(elem.tag) == "Stmt":
            stmts.append(elem)

    for stmt in stmts:
        account_iban = ""
        acct = _find(stmt, "Acct")
        if acct is not None:
            iban_el = _find(acct, "Id/IBAN")
            if iban_el is not None and iban_el.text:
                account_iban = iban_el.text.strip()

        for ntry in stmt:
            if _strip_ns(ntry.tag) != "Ntry":
                continue
            amt_el = _find(ntry, "Amt")
            amount = _parse_amount(amt_el.text) if amt_el is not None and amt_el.text else 0.0
            currency = amt_el.get("Ccy", "EUR") if amt_el is not None else "EUR"

            cdt_dbt_el = _find(ntry, "CdtDbtInd")
            if cdt_dbt_el is not None and cdt_dbt_el.text == "DBIT":
                amount = -abs(amount)
            else:
                amount = abs(amount)

            date_el = _find(ntry, "BookgDt/Dt")
            if date_el is None:
                date_el = _find(ntry, "BookgDt/DtTm")
            if date_el is None:
                date_el = _find(ntry, "ValDt/Dt")
            date_str = date_el.text.strip()[:10] if date_el is not None and date_el.text else ""

            description = ""
            counterparty = ""
            counterparty_iban = ""

            txdtls = _find(ntry, "NtryDtls/TxDtls")
            if txdtls is not None:
                rmt = _find(txdtls, "RmtInf/Ustrd")
                if rmt is not None and rmt.text:
                    description = rmt.text.strip()
                # Debtor / Creditor name depending on direction
                for party_tag in ("RltdPties/Dbtr/Nm", "RltdPties/Cdtr/Nm"):
                    el = _find(txdtls, party_tag)
                    if el is not None and el.text:
                        counterparty = el.text.strip()
                        break
                for iban_tag in (
                    "RltdPties/DbtrAcct/Id/IBAN",
                    "RltdPties/CdtrAcct/Id/IBAN",
                ):
                    el = _find(txdtls, iban_tag)
                    if el is not None and el.text:
                        counterparty_iban = el.text.strip()
                        break

            if not description:
                addtl = _find(ntry, "AddtlNtryInf")
                if addtl is not None and addtl.text:
                    description = addtl.text.strip()

            if not date_str:
                continue

            transactions.append({
                "date": date_str,
                "amount": amount,
                "currency": currency,
                "description": description,
                "counterparty": counterparty,
                "iban": counterparty_iban,
                "account": account_iban,
            })

    return transactions


def parse_file(raw_bytes, filename):
    lower = filename.lower()
    if lower.endswith(".xml"):
        return parse_camt053(raw_bytes, filename)
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return parse_xlsx(raw_bytes, filename)
    return parse_csv(raw_bytes, filename)


def compute_hash(tx):
    key = f"{tx['date']}|{tx['amount']:.2f}|{tx['description']}|{tx['iban']}|{tx['account']}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
