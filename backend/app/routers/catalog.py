from fastapi import APIRouter, Depends

from ..core.catalog import catalog
from ..core.permissions import P, require

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("")
async def get_catalog(
    _=Depends(require(P.CUSTOMERS_CREATE, P.CUSTOMERS_UPDATE, P.INSTALLATIONS_READ, any_of=True)),
):
    """Dealers, equipment makes, panel watts and inverter capacities — the
    choices the customer form, inventory and installation filters offer."""
    return {"success": True, "data": catalog()}
