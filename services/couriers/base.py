# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/services/couriers/base.py

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, NamedTuple

# ADĂUGAT: Clasa lipsă 'TrackingStatus'
class TrackingStatus(NamedTuple):
    """O structură standard pentru a stoca statusul unui AWB."""
    raw_status: str
    derived_status: str
    details: Optional[str] = None

class BaseCourier(ABC):
    """
    Clasă de bază abstractă pentru toți curierii.
    Definește interfața pe care fiecare clasă de curier trebuie să o implementeze.
    """
    def __init__(self, account_key: str):
        self.account_key = account_key

    @abstractmethod
    async def track(self, awb: str) -> Optional[TrackingStatus]:
        """Urmărește un AWB și returnează starea lui."""
        pass

    @abstractmethod
    async def create_awb(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Creează un AWB nou."""
        pass