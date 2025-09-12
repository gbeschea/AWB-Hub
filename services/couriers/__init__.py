# services/couriers/__init__.py

from typing import Optional, Dict, Any
# MODIFICAT: Importăm din 'common.py', nu din 'base.py'
from .common import BaseCourierService 
from .sameday import SamedayCourierService
from .dpd import DPDCourierService

COURIER_MAP = {
    "sameday": SamedayCourierService,
    "dpd": DPDCourierService,
}

def get_courier_service(courier_name: str, account_key: str, settings: Dict[str, Any]) -> Optional[BaseCourierService]:
    if not courier_name:
        return None
    courier_class = COURIER_MAP.get(courier_name.lower())
    if courier_class:
        try:
            return courier_class(account_key=account_key, settings=settings)
        except Exception as e:
            logging.error(f"Failed to instantiate courier '{courier_name}' with account key '{account_key}': {e}")
            return None
    return None