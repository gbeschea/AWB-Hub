# services/couriers/base.py
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict
from datetime import datetime
import httpx
import io

class LabelResponse(ABC):
    """O clasă pentru a standardiza răspunsurile de la API-urile de etichete."""
    def __init__(self, success: bool, content: Optional[io.BytesIO] = None, error_message: Optional[str] = None):
        self.success = success
        self.content = content
        self.error_message = error_message

class TrackingResponse(ABC):
    """O clasă pentru a standardiza răspunsurile de la API-urile de tracking."""
    def __init__(self, status: str, date: Optional[datetime], raw_data: Optional[Dict] = None):
        self.status = status
        self.date = date
        self.raw_data = raw_data

class BaseCourier(ABC):
    """
    Clasa de bază abstractă pentru toți curierii.
    Definește 'contractul' pe care fiecare clasă de curier trebuie să îl implementeze.
    """
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @abstractmethod
    async def get_label(self, awb: str, account_key: Optional[str], paper_size: str) -> LabelResponse:
        """Descarcă eticheta (PDF) pentru un AWB specific."""
        raise NotImplementedError

    @abstractmethod
    async def track_awb(self, awb: str, account_key: Optional[str]) -> TrackingResponse:
        """Returnează statusul curent pentru un AWB specific."""
        raise NotImplementedError
