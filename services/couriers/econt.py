# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/services/couriers/econt.py

import httpx
import logging
from typing import Optional, Dict, Any

from settings import settings
# MODIFICAT: Am schimbat 'CourierTracker' în 'BaseCourier'
from .base import BaseCourier, TrackingStatus

async def track_awb(awb_number: str, account_key: str) -> Optional[TrackingStatus]:
    """
    Interoghează API-ul Econt pentru a obține starea unui AWB.
    """
    if not settings.ECONT_CONFIG:
        logging.error("ECONT_CONFIG nu este setat.")
        return None

    creds = settings.ECONT_CONFIG.get(account_key)
    if not creds:
        logging.error(f"Nu s-au găsit credențiale Econt pentru account_key: {account_key}")
        return None

    url = f"{creds['base_url']}/services/Shipments/ShipmentService.getShipmentStatuses.json"
    payload = {
        "shipmentNumbers": [awb_number],
    }

    async with httpx.AsyncClient(auth=(creds["username"], creds["password"])) as client:
        try:
            response = await client.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            if "shipmentStatuses" in data and data["shipmentStatuses"]:
                status_info = data["shipmentStatuses"][0]
                if "error" in status_info:
                    logging.warning(f"Eroare de la Econt pentru AWB {awb_number}: {status_info['error']['message']}")
                    return None
                
                raw_status = status_info.get("status", {}).get("name", "Unknown")
                return TrackingStatus(
                    raw_status=raw_status,
                    derived_status="unknown" # Va trebui mapat
                )
        except httpx.HTTPStatusError as e:
            logging.error(f"Eroare HTTP la interogarea Econt pentru AWB {awb_number}: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logging.error(f"Eroare la procesarea AWB Econt {awb_number}: {e}")

    return None

# MODIFICAT: Am redenumit clasa în 'EcontCourier' și moștenește 'BaseCourier'
class EcontCourier(BaseCourier):
    async def track(self, awb: str) -> Optional[TrackingStatus]:
        return await track_awb(awb, self.account_key)

    async def create_awb(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logging.warning("Funcționalitatea de creare AWB pentru Econt nu este implementată.")
        return None