# gbeschea/awb-hub/AWB-Hub-4f368a2a96d8f5e58ab53450be45f32021473f5a/services/couriers/sameday.py

import httpx
import logging
import asyncio
import time
from typing import Optional
from datetime import datetime, timedelta, timezone

from .common import BaseCourierService, TrackingStatus

# --- RATE LIMITER GLOBAL PENTRU SAMEDAY ---
# Aceste variabile sunt partajate pentru a limita viteza tuturor cererilor către Sameday
_last_request_time: float = 0.0
_rate_limit_interval: float = 0.5  # Așteaptă cel puțin 0.5 secunde între cereri
_rate_limit_lock = asyncio.Lock()

async def _apply_sameday_rate_limit():
    """Așteaptă dacă este necesar pentru a respecta limita de request-uri."""
    async with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < _rate_limit_interval:
            await asyncio.sleep(_rate_limit_interval - elapsed)
        # Actualizăm timpul ultimei cereri DUPĂ ce am așteptat
        globals()['_last_request_time'] = time.monotonic()


def _parse_sameday_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str: return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

class SamedayCourierService(BaseCourierService):
    """Sameday AWB Tracking Service with authentication and rate limiting."""

    _token: Optional[str] = None
    _token_expiry: datetime = datetime.min.replace(tzinfo=timezone.utc)
    _token_lock = asyncio.Lock()

    def __init__(self, account_key: str, settings: dict):
        super().__init__(account_key, settings)
        
        self.username = self.settings.get('username')
        self.password = self.settings.get('password')
        self.api_url = "https://api.sameday.ro"

        if not self.username or not self.password:
            raise ValueError(f"Username and password are required for Sameday account key: {account_key}.")

    async def _get_token(self) -> Optional[str]:
        async with self._token_lock:
            if self._token and datetime.now(timezone.utc) < self._token_expiry:
                return self._token

            logging.info(f"Se solicită un token nou de la Sameday pentru user: {self.username}")
            try:
                await _apply_sameday_rate_limit() # Aplicăm limitare și la autentificare
                headers = {'X-Auth-Username': self.username, 'X-Auth-Password': self.password}
                async with httpx.AsyncClient() as client:
                    url = f"{self.api_url}/api/authenticate"
                    response = await client.post(url, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    
                    self._token = data.get("token")
                    self._token_expiry = datetime.now(timezone.utc) + timedelta(minutes=55)
                    
                    logging.info(f"Token Sameday obținut cu succes pentru user: {self.username}")
                    return self._token
            except Exception as e:
                logging.error(f"Autentificare Sameday eșuată pentru user '{self.username}': {e}")
                self._token = None
                return None

    async def track(self, awb: str) -> Optional[TrackingStatus]:
        token = await self._get_token()
        if not token:
            return TrackingStatus(raw_status="Eroare Autentificare Sameday")

        headers = {"X-Auth-Token": token}
        
        try:
            await _apply_sameday_rate_limit() # Aplicăm limitarea de viteză ÎNAINTE de cerere
            
            url = f"{self.api_url}/api/client/awb/{awb}/status"
            async with httpx.AsyncClient() as client:
                track_response = await client.get(url, headers=headers)
                
                if track_response.status_code == 404:
                    return TrackingStatus(raw_status="AWB inexistent (client)")
                
                track_response.raise_for_status()
                data = track_response.json()

                history = data.get("expeditionHistory", [])
                if not history:
                    return TrackingStatus(raw_status="AWB generat, fără istoric")

                latest_event = max(history, key=lambda event: _parse_sameday_date(event.get('statusDate')) or datetime.min.replace(tzinfo=timezone.utc))
                raw_status = latest_event.get('statusLabel', "Status necunoscut")
                
                return TrackingStatus(raw_status=raw_status)
        except Exception as e:
            logging.error(f"Eroare generală la tracking Sameday AWB {awb}: {e}")
            return TrackingStatus(raw_status="Eroare generală tracking")