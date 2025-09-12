# gbeschea/awb-hub/AWB-Hub-4f368a2a96d8f5e58ab53450be45f32021473f5a/services/couriers/sameday.py

import httpx
import logging
import asyncio
import time
from typing import Optional
from datetime import datetime, timedelta, timezone

from .common import BaseCourierService, TrackingStatus

def _parse_sameday_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str: return None
    try:
        # Formatul standard ISO 8601
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        try:
            # Format alternativ întâlnit uneori
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

class SamedayCourierService(BaseCourierService):
    """Sameday AWB Tracking Service with proper token management."""

    # Variabile de clasă pentru a stoca token-ul partajat
    _token: Optional[str] = None
    _token_expiry: datetime = datetime.min.replace(tzinfo=timezone.utc)
    _token_lock = asyncio.Lock()

    def __init__(self, account_key: str, settings: dict):
        super().__init__(account_key, settings)
        
        self.username = self.settings.get('username')
        self.password = self.settings.get('password')
        self.api_url = "https://api.sameday.ro"

        if not self.username or not self.password:
            raise ValueError("Username and password are required for Sameday service.")

    async def _get_token(self) -> Optional[str]:
        """
        Obține un token de autentificare, refolosindu-l pe cel existent dacă este valid.
        Acest mecanism previne erorile de 'Too Many Requests'.
        """
        async with self._token_lock:
            # Verificăm dacă token-ul existent mai este valid (expiră în 60 min)
            if self._token and datetime.now(timezone.utc) < self._token_expiry:
                return self._token

            # Dacă token-ul a expirat sau nu există, cerem unul nou
            logging.info(f"Se solicită un token nou de la Sameday pentru user: {self.username}")
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/api/authenticate",
                        json={"username": self.username, "password": self.password}
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    self._token = data.get("token")
                    # Setăm timpul de expirare cu 5 minute mai devreme, pentru siguranță
                    self._token_expiry = datetime.now(timezone.utc) + timedelta(minutes=55)
                    
                    logging.info("Token Sameday obținut cu succes.")
                    return self._token

            except httpx.HTTPStatusError as e:
                logging.error(f"Autentificare Sameday eșuată pentru user '{self.username}': {e}")
                # Resetăm token-ul în caz de eroare pentru a forța reîncercarea data viitoare
                self._token = None
                self._token_expiry = datetime.min.replace(tzinfo=timezone.utc)
                return None

    async def track(self, awb: str) -> Optional[TrackingStatus]:
        token = await self._get_token()
        if not token:
            return TrackingStatus(raw_status="Eroare Autentificare Sameday")

        headers = {"X-Auth-Token": token}
        
        try:
            # Folosim endpoint-ul corect din aplicația veche
            url = f"{self.api_url}/api/awb/track/{awb}"
            async with httpx.AsyncClient() as client:
                track_response = await client.get(url, headers=headers)
                track_response.raise_for_status()
                data = track_response.json()

                history = data.get("awbHistory", [])
                if not history:
                    return TrackingStatus(raw_status="AWB negăsit sau fără istoric")

                # Găsim ultimul eveniment din istoric
                latest_event = max(history, key=lambda event: _parse_sameday_date(event.get('eventDate')) or datetime.min.replace(tzinfo=timezone.utc))
                raw_status = latest_event.get("status", "Status necunoscut")
                
                return TrackingStatus(raw_status=raw_status)

        except httpx.HTTPStatusError as e:
            logging.error(f"Eroare HTTP Sameday pentru AWB {awb}: {e.response.status_code} - {e.response.text}")
            return TrackingStatus(raw_status=f"Eroare HTTP {e.response.status_code}")
        except Exception as e:
            logging.error(f"Eroare generală la tracking Sameday AWB {awb}: {e}")
            return TrackingStatus(raw_status="Eroare generală tracking")