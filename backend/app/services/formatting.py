"""
How stored values are printed — the one place that turns typed data into text
for documents, the Customer Details sheet and inventory labels.

Units are NOT added here for capacities and watts: the DOCX templates already
carry them ("${SOLAR_CAPACITY}$ kW", "${INVERTER_CAPACITY}$ KW model", ...), so
the value alone is printed.
"""
from datetime import date


def fmt_number(n) -> str:
    """5.0 -> '5', 3.30 -> '3.3', 3.245 -> '3.245'. None -> ''."""
    if n is None:
        return ""
    return f"{float(n):.3f}".rstrip("0").rstrip(".")


def fmt_inr(n) -> str:
    """Whole rupees with Indian grouping: 150000 -> '1,50,000'. None -> ''."""
    if n is None:
        return ""
    whole = str(int(n))
    if len(whole) <= 3:
        return whole
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def fmt_date(iso) -> str:
    """'2026-03-15' -> '15-03-2026'. None -> ''."""
    if not iso:
        return ""
    return date.fromisoformat(str(iso)[:10]).strftime("%d-%m-%Y")


def fmt_years(n) -> str:
    """Guarantee: 10 -> '10 YEAR' (the wording the documents have always used)."""
    return "" if n is None else f"{int(n)} YEAR"


# Field -> formatter. Every field not listed here is text and printed as-is.
DOCUMENT_FORMATS = {
    "SYSTEM_COST":           fmt_inr,
    "AGREEMENT_SYSTEM_COST": fmt_inr,
    "SOLAR_CAPACITY":        fmt_number,
    "SANCTIONED_CAPACITY":   fmt_number,
    "INVERTER_CAPACITY":     fmt_number,
    "PANEL_WATT":            fmt_number,
    "NO_OF_PANEL":           fmt_number,
    "TOTAL_PANEL_CAPACITY":  fmt_number,
    "INVERTER_GUARANTEE":    fmt_years,
    "PANEL_GUARANTEE":       fmt_years,
    "CONSUMER_APP_DATE":     fmt_date,
    "SUBSIDY_APP_DATE":      fmt_date,
    "INSTALLATION_DATE":     fmt_date,
}


def document_value(key: str, value) -> str:
    """One customer field as it appears on a document ('' when blank)."""
    if value is None:
        return ""
    fmt = DOCUMENT_FORMATS.get(key)
    return fmt(value) if fmt else str(value).strip()
