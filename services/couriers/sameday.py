import httpx
import logging
from typing import Optional

from .common import BaseCourierService, TrackingStatus

# AM ȘTERS IMPORTUL: from settings import settings

class SamedayCourierService(BaseCourierService):
    """Sameday AWB Tracking Service."""

    # MODIFICARE: Constructorul primește acum un dicționar 'settings'
    def __init__(self, account_key: str, settings: dict):
        super().__init__(account_key)
        # Acreditările sunt luate din dicționar, nu din fișierul global
        self.username = settings.get('username')
        self.password = settings.get('password')
        self.api_url = "https://api.sameday.ro"

        # Validare esențială pentru a preveni erorile
        if not self.username or not self.password:
            raise ValueError("Username and password are required for Sameday service.")

    async def track(self, awb: str) -> Optional[TrackingStatus]:
        headers = {}
        try:
            async with httpx.AsyncClient() as client:
                # Pasul 1: Autentificare
                auth_response = await client.post(
                    f"{self.api_url}/api/authenticate",
                    json={"username": self.username, "password": self.password}
                )
                auth_response.raise_for_status()
                token = auth_response.json().get("token")
                headers["X-Auth-Token"] = token

                # Pasul 2: Urmărire AWB
                track_response = await client.get(
                    f"{self.api_url}/api/awb/track/{awb}",
                    headers=headers
                )
                track_response.raise_for_status()
                data = track_response.json()

                raw_status = data.get("awbHistory", [{}])[-1].get("status", "Unknown")
                return TrackingStatus(raw_status=raw_status)

        except httpx.HTTPStatusError as e:
            logging.error(f"Sameday HTTP Error for AWB {awb}: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logging.error(f"General error tracking Sameday AWB {awb}: {e}")
            return None