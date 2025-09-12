# services/couriers/__init__.py
from typing import Optional
import httpx
from .base import BaseCourier
from .dpd import DPDCourier
from .sameday import SamedayCourier
from .econt import EcontCourier

# Un singur client HTTP partajat pentru toată aplicația, pentru performanță
_http_client = httpx.AsyncClient(timeout=45.0)

# --- MODIFICARE: Creăm instanțe unice (singletons) pentru fiecare curier ---
_courier_instances = {
    "dpd": DPDCourier(_http_client),
    "sameday": SamedayCourier(_http_client),
    "econt": EcontCourier(_http_client),
}
# --- SFÂRȘIT MODIFICARE ---


def get_courier_service(courier_key: str) -> Optional[BaseCourier]:
    """
    Funcția Fabrică (Factory Function).
    Acum returnează o instanță partajată, nu una nouă.
    """
    if not courier_key:
        return None
        
    # Caută o potrivire parțială (ex: 'dpd-ro' se va potrivi cu 'dpd')
    # --- MODIFICARE: Căutăm și returnăm instanța existentă ---
    for key, instance in _courier_instances.items():
        if key in courier_key.lower():
            return instance
    # --- SFÂRȘIT MODIFICARE ---
    
    return None