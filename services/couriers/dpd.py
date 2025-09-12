# services/couriers/dpd.py
import httpx
import logging
from typing import Optional
from datetime import datetime, timezone
from .common import BaseCourierService, TrackingStatus

def _parse_dpd_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str: return None
    try:
        # DPD returnează data în format ISO 8601 cu 'Z'
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None

class DPDCourierService(BaseCourierService):
    """DPD AWB Tracking Service - implementat cu logica ta originală."""
    
    def __init__(self, account_key: str, settings: dict):
        super().__init__(account_key, settings)
        self.username = self.settings.get('username')
        self.password = self.settings.get('password')
        self.api_url = "https://api.dpd.ro/v1"

        if not all([self.username, self.password]):
            raise ValueError(f"Username/password missing for DPD account {account_key}")

    async def track(self, awb: str) -> Optional[TrackingStatus]:
        body = {
            'userName': self.username, 
            'password': self.password, 
            'language': 'RO', # Schimbat în RO pentru mesaje mai clare
            'parcels': [{'id': awb}]
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f'{self.api_url}/track/', json=body, timeout=15.0)
                
                if r.status_code != 200:
                    logging.error(f"DPD HTTP Error for AWB {awb}: {r.status_code} - {r.text}")
                    return TrackingStatus(raw_status=f"Eroare HTTP DPD: {r.status_code}")
                
                data = (r.json() or {}).get('parcels', [{}])[0]
                operations = data.get('operations', [])
                
                if not operations:
                    return TrackingStatus(raw_status="AWB negăsit sau fără istoric DPD")

                last_op = operations[-1]
                raw_status = (last_op.get('description') or 'N/A').strip()
                return TrackingStatus(raw_status=raw_status)

        except Exception as e:
            logging.error(f"General error tracking DPD AWB {awb}: {e}")
            return TrackingStatus(raw_status="Eroare generală la tracking DPD")