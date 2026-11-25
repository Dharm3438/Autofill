from pydantic import BaseModel, EmailStr
from typing import Optional, List, Literal, Union
from datetime import date


# Fields the customer form requires (they all appear on the printable Customer
# Details sheet). Email is deliberately optional. Enforced by the customers
# router on create, and on update so a required field can't be blanked out.
REQUIRED_CUSTOMER_FIELDS = {
    "CONSUMER_NAME":     "Consumer Name",
    "CONSUMER_ADDRESS":  "Address",
    "CONSUMER_PHONE":    "Phone",
    "CONSUMER_AADHAR":   "Aadhar Number",
    "CONSUMER_NO":       "Consumer No",
    "DEALER_NAME":       "Dealer Name",
    "CONSUMER_APP_NO":   "Application No",
    "CONSUMER_APP_DATE": "Application Date",
    "SOLAR_CAPACITY":    "Solar Capacity",
    "INVERTER_MAKE":     "Inverter Make",
    "INVERTER_CAPACITY": "Inverter Capacity",
    "PANEL_COMPANY":     "Panel Company",
    "PANEL_WATT":        "Panel Watt",
    "NO_OF_PANEL":       "No of Panels",
    "SYSTEM_COST":       "System Cost",
}


def missing_required_fields(data: dict, partial: bool = False) -> List[str]:
    """
    Labels of required fields that are blank in `data`.
    partial=True (updates): only fields actually sent are checked, so an
    omitted field is fine but one sent as an empty string is not.
    """
    missing = []
    for key, label in REQUIRED_CUSTOMER_FIELDS.items():
        value = data.get(key)
        if partial and value is None:
            continue
        if value is None or not str(value).strip():
            missing.append(label)
    return missing


class CustomerCreate(BaseModel):
    CONSUMER_NAME: str
    CONSUMER_ADDRESS: str
    CONSUMER_PHONE: str
    # Email is optional; the form sends "" when it's left empty.
    CONSUMER_EMAIL: Optional[Union[EmailStr, Literal[""]]] = None
    CONSUMER_AADHAR: Optional[str] = None
    CONSUMER_NO: Optional[str] = None
    DEALER_NAME: Optional[str] = None
    SANCTIONED_CAPACITY: Optional[str] = None
    CONSUMER_APP_DATE: Optional[str] = None
    CONSUMER_APP_NO: Optional[str] = None
    # PM Surya Ghar subsidy portal application. Optional; shown only on the
    # Customer Details sheet. Documents keep using CONSUMER_APP_NO/DATE.
    SUBSIDY_APP_NO: Optional[str] = None
    SUBSIDY_APP_DATE: Optional[str] = None
    SOLAR_CAPACITY: Optional[str] = None
    INVERTER_MAKE: Optional[str] = None
    INVERTER_CAPACITY: Optional[str] = None
    INVERTER_GURANTEE: Optional[str] = None
    INVERTER_SR_NO: Optional[str] = None
    PANEL_COMPANY: Optional[str] = None
    PANEL_WATT: Optional[str] = None
    NO_OF_PANEL: Optional[str] = None
    TOTAL_PANEL_CAPACITY: Optional[str] = None
    PANEL_SR_NO: Optional[str] = None
    PANEL_GURANTEE: Optional[str] = None
    INSTALLATION_DATE: Optional[str] = None
    INSTALLATION_CITY: Optional[str] = None
    INSTALLATION_DISTRICT: Optional[str] = None
    DISCOM_REGISTERED_OFFICE: Optional[str] = None
    SYSTEM_COST: Optional[str] = None
    # Amount printed on the documents (Net-Metering Agreement). Separate from
    # SYSTEM_COST, which is the real price used for payments and is never put
    # on a generated document. Documents role / admin only.
    AGREEMENT_SYSTEM_COST: Optional[str] = None
    METER_TESTING_DATE: Optional[str] = None
    METER_RECIPT_NO: Optional[str] = None
    GENERATION_METER_MAKE: Optional[str] = None
    GENERATION_METER_NO: Optional[str] = None


class CustomerUpdate(CustomerCreate):
    CONSUMER_NAME: Optional[str] = None
    CONSUMER_ADDRESS: Optional[str] = None
    CONSUMER_PHONE: Optional[str] = None


class UploadStatus(BaseModel):
    installation: bool = False
    np_stamp: bool = False
    dcr: bool = False


class CustomerOut(CustomerCreate):
    id: str
    doc_status: str = "none"       # none | generating | complete
    signing_status: str = "none"   # none | sent | signed
    uploads: UploadStatus = UploadStatus()
    installation_steps: Optional[List[dict]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
