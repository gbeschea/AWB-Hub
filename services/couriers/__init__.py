# gbeschea/awb-hub/AWB-Hub-4f368a2a96d8f5e58ab53450be45f32021473f5a/services/couriers/__init__.py

import logging
from typing import Dict, Any, Optional

from .common import BaseCourierService
from .dpd import DPDCourierService
from .sameday import SamedayCourierService
# Adaugă și alți curieri aici
# from .econt import EcontCourierService

# Un dicționar partajat pentru a stoca instanțele unice (singletons) ale serviciilor
_courier_instances: Dict[str, BaseCourierService] = {}

def get_courier_service(courier_type: str, account_key: str, credentials: Dict[str, Any]) -> Optional[BaseCourierService]:
    """
    Funcție Fabrică (Factory).
    Creează sau returnează o instanță unică pentru fiecare cont de curier.
    """
    if not courier_type or not account_key:
        return None

    # Cheia unică pentru o instanță este combinația tip-cont
    instance_key = f"{courier_type.lower()}_{account_key}"

    if instance_key not in _courier_instances:
        logging.info(f"Se creează o instanță nouă de serviciu pentru: {instance_key}")
        
        service_class = None
        if courier_type.lower() == 'sameday':
            service_class = SamedayCourierService
        elif courier_type.lower() == 'dpd':
            service_class = DPDCourierService
        # Adaugă `elif` pentru alți curieri
        
        if service_class:
            _courier_instances[instance_key] = service_class(account_key, credentials)
        else:
            logging.warning(f"Tipul de curier '{courier_type}' nu este implementat în __init__.py")
            return None
            
    return _courier_instances[instance_key]