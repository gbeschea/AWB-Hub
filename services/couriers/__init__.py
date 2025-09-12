# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/services/couriers/__init__.py

from typing import Optional
from .base import BaseCourier
from .sameday import SamedayCourier
from .dpd import DPDCourier
from .econt import EcontCourier

COURIER_MAP = {
    "sameday": SamedayCourier,
    "dpd": DPDCourier,
    "econt": EcontCourier,
}

# MODIFICAT: Am adăugat 'account_key: str' la semnătura funcției
def get_courier_service(courier_name: str, account_key: str) -> Optional[BaseCourier]:
    """Factory function to get a courier service instance."""
    courier_class = COURIER_MAP.get(courier_name.lower())
    if courier_class:
        # Pasăm 'account_key' la inițializarea clasei
        return courier_class(account_key=account_key)
    return None