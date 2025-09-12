import io
import logging
import asyncio
import json
import time
from typing import Optional
from datetime import datetime, timezone
from .base import BaseCourier, LabelResponse, TrackingResponse
from settings import settings

def _parse_sameday_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str: return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

class SamedayCourier(BaseCourier):
    _token: Optional[str] = None
    _token_time: datetime = datetime.min
    _token_lock = asyncio.Lock()

    _last_request_time: float = 0.0
    _rate_limit_interval: float = 0.3 # 1 request pe 1.1 secunde pentru siguranță
    _rate_limit_lock = asyncio.Lock()

    async def _apply_rate_limit(self):
        """Așteaptă dacă este necesar pentru a respecta limita de request-uri."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._rate_limit_interval:
                await asyncio.sleep(self._rate_limit_interval - elapsed)
            self._last_request_time = time.monotonic()

    async def _get_token(self) -> Optional[str]:
        """Obține și gestionează token-ul de autentificare Sameday, prevenind race conditions."""
        async with self._token_lock:
            if self._token and (datetime.now() - self._token_time).total_seconds() < 3600:
                return self._token
            
            creds = settings.SAMEDAY_CREDS
            if not creds:
                logging.error("Credențialele Sameday nu sunt configurate.")
                return None
            try:
                await self._apply_rate_limit()
                r = await self.client.post(
                    'https://api.sameday.ro/api/authenticate',
                    headers={'X-AUTH-USERNAME': creds['username'], 'X-AUTH-PASSWORD': creds['password']}
                )
                if r.status_code == 200:
                    self._token = (r.json() or {}).get('token')
                    self._token_time = datetime.now()
                    return self._token
                
                logging.error(f"Autentificare Sameday eșuată cu status {r.status_code}: {r.text}")
                return None
            except Exception as e:
                logging.error(f"Eroare la obținerea token-ului Sameday: {e}")
                return None

    async def get_label(self, awb: str, account_key: Optional[str], paper_size: str) -> LabelResponse:
        token = await self._get_token()
        if not token:
            return LabelResponse(success=False, error_message="Autentificare Sameday eșuată.")

        valid_paper_size = paper_size.upper() if paper_size.upper() in ["A4", "A6"] else "A6"
        url = f'https://api.sameday.ro/api/awb/download/{awb}/{valid_paper_size}'
        try:
            await self._apply_rate_limit()
            r = await self.client.get(url, headers={'X-AUTH-TOKEN': token}, timeout=30, follow_redirects=True)
            
            if r.status_code == 200 and 'application/pdf' in r.headers.get('content-type', ''):
                return LabelResponse(success=True, content=io.BytesIO(r.content))

            try:
                error_msg = r.json().get('message', 'Răspuns necunoscut')
            except json.JSONDecodeError:
                error_msg = "Răspuns neașteptat de la Sameday (HTML sau text primit în loc de PDF)."
            
            return LabelResponse(success=False, error_message=error_msg)

        except Exception as e:
            return LabelResponse(success=False, error_message=f"Excepție la descărcare etichetă Sameday: {e}")

    async def track_awb(self, awb: str, account_key: Optional[str]) -> TrackingResponse:
        token = await self._get_token()
        if not token:
            return TrackingResponse(status='Eroare Autentificare', date=None)

        try:
            await self._apply_rate_limit()
            url = f'https://api.sameday.ro/api/client/awb/{awb}/status'
            r = await self.client.get(url, headers={'X-AUTH-TOKEN': token}, timeout=15.0)
            if r.status_code != 200:
                return TrackingResponse(status=f'HTTP {r.status_code}', date=None)
            
            response_data = r.json()
            history = response_data.get('expeditionHistory', [])
            if not history:
                return TrackingResponse(status='AWB Generat', date=None, raw_data=response_data)

            latest_event = max(history, key=lambda event: _parse_sameday_date(event.get('statusDate')) or datetime.min.replace(tzinfo=timezone.utc))
            status_label = latest_event.get('statusLabel', 'Status neclar')
            status_date = _parse_sameday_date(latest_event.get('statusDate'))

            return TrackingResponse(status=status_label, date=status_date, raw_data=response_data)
        except Exception as e:
            logging.error(f"Eroare la tracking Sameday pentru AWB {awb}: {e}")
            return TrackingResponse(status='Eroare API', date=None)