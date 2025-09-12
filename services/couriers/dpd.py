# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/services/couriers/dpd.py

import httpx
import logging
from typing import Optional, Dict, Any

from settings import settings
# MODIFICAT: Am schimbat 'CourierTracker' în 'BaseCourier'
from .common import BaseCourierService, TrackingStatus

async def track_awb(awb_number: str, account_key: str) -> Optional[TrackingStatus]:
    if not settings.DPD_CONFIG:
        logging.error("DPD_CONFIG nu este setat.")
        return None

    creds = settings.DPD_CONFIG.get(account_key)
    if not creds:
        logging.error(f"Nu s-au găsit credențiale DPD pentru account_key: {account_key}")
        return None

    url = f"{creds['base_url']}/tracking?type=3&doc_id={awb_number}&cons_type=0&lang=ro"
    headers = {
        'User-Agent': creds['user_agent'],
        'Cookie': f"user_lang=ro_RO; lang=ro_RO; auth={creds['auth_token']}"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            if not data or not data.get('status'):
                return None
            
            raw_status = data['status']
            return TrackingStatus(
                raw_status=raw_status,
                derived_status="unknown"
            )
        except httpx.HTTPStatusError as e:
            logging.error(f"Eroare HTTP la interogarea DPD pentru AWB {awb_number}: {e.response.status_code}")
        except Exception as e:
            logging.error(f"Eroare la procesarea AWB DPD {awb_number}: {e}")
            
    return None

# MODIFICAT: Am redenumit clasa în 'DPDCourier' și moștenește 'BaseCourier'
class DPDCourierService(BaseCourierService):
    async def track(self, awb: str) -> Optional[TrackingStatus]:
        return await track_awb(awb, self.account_key)

    async def create_awb(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Aici va veni logica pentru crearea AWB-ului la DPD
        logging.warning("Funcționalitatea de creare AWB pentru DPD nu este implementată.")
        return None