"""
Customer data model.

Every field is stored with a real type so the database can sort, filter and
calculate on it directly:

  • money      — whole rupees (int):        SYSTEM_COST, AGREEMENT_SYSTEM_COST
  • capacity   — kW (float):                SOLAR_CAPACITY, SANCTIONED_CAPACITY, INVERTER_CAPACITY
  • counts     — int:                       PANEL_WATT (W per panel), NO_OF_PANEL
  • dates      — "YYYY-MM-DD" (validated):  CONSUMER_APP_DATE, SUBSIDY_APP_DATE
  • ids        — normalised text:           phone = 10 digits, Aadhaar = 12 digits, consumer no without spaces
  • choices    — must be an active item of the admin-managed catalog (catalog_items):
                 dealer, inverter make/capacity, panel company/watt
                 (checked by services/catalog_rules.py, which needs the database)
  • serials    — comma-separated text ("A1, A2, A3")
  • blank      — stored as null, never ""

Derived on the server at every save (never accepted from the client):
  TOTAL_PANEL_CAPACITY (W), INVERTER_GUARANTEE / PANEL_GUARANTEE (years, from
  the make's warranty in the catalog).

How these values are printed (DD-MM-YYYY, 1,50,000, ...) is decided in one
place: services/formatting.py.
"""
import re
from datetime import date
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, BeforeValidator, EmailStr, Field



# Admin-facing label for every customer field. Used in validation messages and
# the "missing fields" report before document generation.
FIELD_LABELS = {
    "CONSUMER_NAME":            "Consumer Name",
    "CONSUMER_ADDRESS":         "Address",
    "CONSUMER_PHONE":           "Phone",
    "CONSUMER_EMAIL":           "Email",
    "CONSUMER_AADHAR":          "Aadhaar Number",
    "CONSUMER_NO":              "Consumer No",
    "DEALER_NAME":              "Dealer Name",
    "CONSUMER_APP_NO":          "Application No",
    "CONSUMER_APP_DATE":        "Application Date",
    "SUBSIDY_APP_NO":           "Subsidy Portal Application No",
    "SUBSIDY_APP_DATE":         "Subsidy Portal Application Date",
    "SANCTIONED_CAPACITY":      "Sanctioned Capacity",
    "SOLAR_CAPACITY":           "Solar Capacity",
    "INVERTER_MAKE":            "Inverter Make",
    "INVERTER_CAPACITY":        "Inverter Capacity",
    "INVERTER_GUARANTEE":       "Inverter Guarantee",
    "INVERTER_SR_NO":           "Inverter Serial No",
    "PANEL_COMPANY":            "Panel Company",
    "PANEL_WATT":               "Panel Watt",
    "NO_OF_PANEL":              "No of Panels",
    "TOTAL_PANEL_CAPACITY":     "Total Panel Capacity",
    "PANEL_SR_NO":              "Panel Serial No",
    "PANEL_GUARANTEE":          "Panel Guarantee",
    "CELL_MANUFACTURER":        "Cell Manufacturer",
    "INSTALLATION_DATE":        "Installation Date",
    "INSTALLATION_CITY":        "Installation City",
    "INSTALLATION_DISTRICT":    "Installation District",
    "DISCOM_REGISTERED_OFFICE": "DISCOM Registered Office",
    "SYSTEM_COST":              "System Cost",
    "AGREEMENT_SYSTEM_COST":    "Agreement System Cost",
}


def field_label(key: str) -> str:
    return FIELD_LABELS.get(key) or key.replace("_", " ").title()


# Fields the customer form requires (they all appear on the printable Customer
# Details sheet). Email and application no/date are deliberately optional. Enforced on create, and on
# update so a required field can't be blanked out.
REQUIRED_CUSTOMER_FIELDS = (
    "CONSUMER_NAME", "CONSUMER_ADDRESS", "CONSUMER_PHONE", "CONSUMER_AADHAR",
    "CONSUMER_NO", "DEALER_NAME",
    "SOLAR_CAPACITY", "INVERTER_MAKE", "INVERTER_CAPACITY", "PANEL_COMPANY",
    "PANEL_WATT", "NO_OF_PANEL", "SYSTEM_COST",
)


def missing_required_fields(data: dict, partial: bool = False) -> List[str]:
    """
    Labels of required fields that are blank (None) in `data`.
    partial=True (updates): `data` holds only the fields that were sent, so an
    omitted field is fine but one sent blank is not.
    """
    return [
        field_label(key)
        for key in REQUIRED_CUSTOMER_FIELDS
        if (key in data if partial else True) and data.get(key) is None
    ]


# ── Field types ───────────────────────────────────────────────────────────────

def _blank_to_none(v):
    """The form sends "" for an empty box: store that as null."""
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _phone(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    digits = re.sub(r"[\s\-().]", "", v)
    if digits.startswith("+91"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"\d{10}", digits):
        raise ValueError("must be a 10-digit mobile number")
    return digits


def _aadhaar(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    digits = re.sub(r"[\s\-]", "", v)
    if not re.fullmatch(r"\d{12}", digits):
        raise ValueError("must be 12 digits")
    return digits


def _no_spaces(v: Optional[str]) -> Optional[str]:
    return None if v is None else re.sub(r"\s+", "", v) or None


def normalize_serials(v: Optional[str]) -> Optional[str]:
    """'A1,A2 ,  A3\\nA4' -> 'A1, A2, A3, A4' (commas or new lines separate)."""
    if v is None:
        return None
    parts = [p.strip() for p in re.split(r"[,\n]", v)]
    return ", ".join(p for p in parts if p) or None


def _round_kw(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(v, 3)


Blank = BeforeValidator(_blank_to_none)
Text = Annotated[Optional[str], Blank]
Rupees = Annotated[Optional[Annotated[int, Field(ge=0)]], Blank]
Kw = Annotated[Optional[Annotated[float, Field(gt=0, le=10000)]], Blank, AfterValidator(_round_kw)]
Count = Annotated[Optional[Annotated[int, Field(ge=1)]], Blank]
Day = Annotated[Optional[date], Blank]
# A validated date that stays a "YYYY-MM-DD" string after validation (for
# models whose values are stored as-is rather than through to_store()).
IsoDay = Annotated[Day, AfterValidator(lambda d: d.isoformat() if d else None)]
Serials = Annotated[Optional[str], Blank, AfterValidator(normalize_serials)]


class CustomerCreate(BaseModel):
    CONSUMER_NAME: Text = None
    CONSUMER_ADDRESS: Text = None
    CONSUMER_PHONE: Annotated[Text, AfterValidator(_phone)] = None
    CONSUMER_EMAIL: Annotated[Optional[EmailStr], Blank] = None
    CONSUMER_AADHAR: Annotated[Text, AfterValidator(_aadhaar)] = None
    CONSUMER_NO: Annotated[Text, AfterValidator(_no_spaces)] = None
    DEALER_NAME: Text = None
    SANCTIONED_CAPACITY: Kw = None
    CONSUMER_APP_NO: Text = None
    CONSUMER_APP_DATE: Day = None
    # PM Surya Ghar subsidy portal application. Optional; shown only on the
    # Customer Details sheet. Documents keep using CONSUMER_APP_NO/DATE.
    SUBSIDY_APP_NO: Text = None
    SUBSIDY_APP_DATE: Day = None
    SOLAR_CAPACITY: Kw = None
    INVERTER_MAKE: Text = None
    INVERTER_CAPACITY: Kw = None
    INVERTER_SR_NO: Serials = None
    PANEL_COMPANY: Text = None
    PANEL_WATT: Count = None
    NO_OF_PANEL: Count = None
    PANEL_SR_NO: Serials = None
    INSTALLATION_CITY: Text = None
    INSTALLATION_DISTRICT: Text = None
    DISCOM_REGISTERED_OFFICE: Text = None
    # The real price, used for payments. Never printed on a generated document.
    SYSTEM_COST: Rupees = None
    # Amount printed on the documents (Net-Metering Agreement). Documents role /
    # admin only (see customers router).
    AGREEMENT_SYSTEM_COST: Rupees = None

    def to_store(self, only_sent: bool = False) -> dict:
        """Values as stored in MongoDB (dates as "YYYY-MM-DD").
        only_sent=True (updates): just the fields the request included."""
        return self.model_dump(mode="json", exclude_unset=only_sent)


class CustomerUpdate(CustomerCreate):
    pass


def derived_fields(customer: dict, warranty_years=lambda list_type, make: None) -> dict:
    """Values calculated from other fields. Recomputed on every save from the
    full (merged) customer, so they can never disagree with their inputs.
    `warranty_years(list_type, make)` looks a make's warranty up in the catalog."""
    watt, qty = customer.get("PANEL_WATT"), customer.get("NO_OF_PANEL")
    return {
        "TOTAL_PANEL_CAPACITY": watt * qty if watt and qty else None,
        "INVERTER_GUARANTEE": warranty_years("inverter_make", customer.get("INVERTER_MAKE")),
        "PANEL_GUARANTEE": warranty_years("panel_company", customer.get("PANEL_COMPANY")),
    }
