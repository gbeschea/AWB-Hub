# services/couriers/sameday.py

import httpx
import logging
import asyncio
import time
from typing import Optional
from datetime import datetime, timedelta, timezone

from .common import BaseCourierService, TrackingStatus

# Funcție helper preluată direct din fișierul tău funcțional
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
    """Sameday AWB Tracking Service - varianta corectată cu logica ta originală de caching."""

    # Variabilele sunt la nivel de CLASĂ. Asta era cheia!
    _token: Optional[str] = None
    _token_time: datetime = datetime.min.replace(tzinfo=timezone.utc)
    _token_lock = asyncio.Lock()

    _last_request_time: float = 0.0
    _rate_limit_interval: float = 0.3
    _rate_limit_lock = asyncio.Lock()

    def __init__(self, account_key: str, settings: dict):
        super().__init__(account_key, settings)
        self.username = self.settings.get('username')
        self.password = self.settings.get('password')
        self.api_url = "https://api.sameday.ro"

        if not self.username or not self.password:
            raise ValueError(f"Username/password missing for Sameday account {account_key}")

    async def _apply_rate_limit(self):
        # Folosim self.__class__ pentru a accesa variabilele de clasă, exact ca în codul tău
        async with self.__class__._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self.__class__._last_request_time
            if elapsed < self._rate_limit_interval:
                await asyncio.sleep(self._rate_limit_interval - elapsed)
            self.__class__._last_request_time = time.monotonic()

    async def _get_token(self) -> Optional[str]:
        """Obține un token, refolosindu-l dacă este valid (logica ta originală)."""
        async with self.__class__._token_lock:
            if self.__class__._token and (datetime.now(timezone.utc) - self.__class__._token_time) < timedelta(minutes=50):
                return self.__class__._token

            logging.info(f"Obtaining a new Sameday token for user '{self.username}'...")
            try:
                await self._apply_rate_limit()
                async with httpx.AsyncClient() as client:
                    auth_response = await client.post(
                        f"{self.api_url}/api/authenticate",
                        json={"username": self.username, "password": self.password}
                    )
                    auth_response.raise_for_status()
                    token_data = auth_response.json()
                    self.__class__._token = token_data.get("token")
                    self.__class__._token_time = datetime.now(timezone.utc)
                    logging.info("Successfully obtained new Sameday token.")
                    return self.__class__._token
            except Exception as e:
                logging.error(f"Sameday authentication failed for user '{self.username}': {e}")
                self.__class__._token = None
                return None

    async def track(self, awb: str) -> Optional[TrackingStatus]:
        token = await self._get_token()
        if not token:
            return TrackingStatus(raw_status="Eroare Autentificare Sameday")

        try:
            await self._apply_rate_limit()
            async with httpx.AsyncClient() as client:
                headers = {"X-Auth-Token": token}
                url = f'https://api.sameday.ro/api/client/awb/{awb}/status'
                track_response = await client.get(url, headers=headers)
                track_response.raise_for_status()
                data = track_response.json()

                history = data.get("expeditionHistory", [])
                if not history:
                    return TrackingStatus(raw_status="AWB negăsit sau fără istoric")

                latest_event = max(history, key=lambda event: _parse_sameday_date(event.get('statusDate')) or datetime.min.replace(tzinfo=timezone.utc))
                raw_status = latest_event.get("statusLabel", "Status necunoscut")
                return TrackingStatus(raw_status=raw_status)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                async with self.__class__._token_lock:
                    self.__class__._token = None # Invalidează token-ul
            logging.error(f"Sameday HTTP Error for AWB {awb}: {e.response.status_code} - {e.response.text}")
            return TrackingStatus(raw_status=f"Eroare HTTP: {e.response.status_code}")
        except Exception as e:
            logging.error(f"General error tracking Sameday AWB {awb}: {e}")
            return TrackingStatus(raw_status="Eroare generală la tracking")