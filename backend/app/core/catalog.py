"""
The fixed choice lists: dealers, equipment makes (with their warranty), panel
wattages and inverter capacities.

Single source of truth. The server validates customer data against these lists
and the frontend reads them from GET /api/catalog to build its dropdowns, so a
value outside the list can't be saved (inventory groups by exact value, so a
stray spelling would otherwise split a stock line in two).

To add a make, dealer, wattage or capacity, add it here — nothing else.
"""

DEALERS = [
    "Devicharan Katkar",
    "Sadguru electronic",
    "Pravin Ranalkar",
    "Rajesh Khona Pachora",
    "Somnath Chaudhary",
    "Santosh Gadia",
    "Nilkanth Salunkhe",
    "Adiwal Pachora",
    "Balasaheb Karmad",
    "Satish Khairnar Bhoras",
    "Sudhir kumbhar",
    "Sagar Rajput",
    "Office",
]

# make -> warranty in years (stored on the customer as *_GUARANTEE when saved)
INVERTER_MAKES = {
    "UTL": 10,
    "WAAREE": 10,
    "APS": 10,
    "KSOLARE": 10,
    "GOODWE": 10,
    "Xwatt": 10,
    "Polycab": 8,
    "Microtek Inverter": 10,
    "Pv blink": 10,
}

PANEL_MAKES = {
    "UTL": 27,
    "ADANI": 30,
    "WAAREE": 30,
    "TATA": 30,
    "PREMIER": 30,
    "APS": 30,
}

# Watts per panel
PANEL_WATTS = [500, 525, 530, 540, 545, 550, 570, 575, 580, 585, 590, 600, 610, 615, 620]

# Inverter capacity in kW
INVERTER_CAPACITIES = [1, 2, 3, 3.3, 3.6, 4, 4.6, 5, 5.5, 6, 8, 10, 12, 15, 20]


def catalog() -> dict:
    """The lists as sent to the frontend."""
    return {
        "dealers": DEALERS,
        "inverter_makes": [{"name": k, "warranty_years": v} for k, v in INVERTER_MAKES.items()],
        "panel_makes": [{"name": k, "warranty_years": v} for k, v in PANEL_MAKES.items()],
        "panel_watts": PANEL_WATTS,
        "inverter_capacities": INVERTER_CAPACITIES,
    }
