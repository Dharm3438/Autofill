from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date


class CustomerCreate(BaseModel):
    CONSUMER_NAME: str
    CONSUMER_ADDRESS: str
    CONSUMER_PHONE: str
    CONSUMER_EMAIL: Optional[EmailStr] = None
    CONSUMER_AADHAR: Optional[str] = None
    CONSUMER_NO: Optional[str] = None
    DEALER_NAME: Optional[str] = None
    SANCTIONED_CAPACITY: Optional[str] = None
    CONSUMER_APP_DATE: Optional[str] = None
    CONSUMER_APP_NO: Optional[str] = None
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
    CELL_MANUFACTURER: Optional[str] = None
    PANEL_GURANTEE: Optional[str] = None
    INSTALLATION_DATE: Optional[str] = None
    INSTALLATION_CITY: Optional[str] = None
    INSTALLATION_DISTRICT: Optional[str] = None
    DISCOM_REGISTERED_OFFICE: Optional[str] = None
    SYSTEM_COST: Optional[str] = None
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
