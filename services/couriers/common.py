# services/couriers/common.py

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

class TrackingStatus(BaseModel):
    """
    O structură standard pentru răspunsul de la serviciile de tracking.
    """
    raw_status: str

class BaseCourierService(ABC):
    """
    Clasa de bază abstractă pentru toate serviciile de curierat.
    Definește interfața comună.
    """
    def __init__(self, account_key: str, settings: dict):
        self.account_key = account_key
        self.settings = settings

    @abstractmethod
    async def track(self, awb: str) -> Optional[TrackingStatus]:
        """Urmărește un AWB și returnează statusul brut."""
        pass

    # Poți adăuga aici și alte metode comune, cum ar fi 'create_awb'
    # @abstractmethod
    # async def create_awb(self, data: dict) -> Optional[dict]:
    #     pass