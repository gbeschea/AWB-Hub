# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/services/couriers/sameday.py

import httpx
import logging
from typing import Optional, Dict, Any

from settings import settings
# MODIFICAT: Am schimbat 'CourierTracker' în 'BaseCourier'
from .base import BaseCourier, TrackingStatus

# Cache simplu în memorie pentru token-ul Sameday
sameday_token_cache: Dict[str, str] = {}

async def login_sameday(account_key: str) -> Optional[str]:
    """
    Obține un token de autentificare de la Sameday.
    """
    if account_key in sameday_token_cache:
        return sameday_token_cache[account_key]

    if not settings.SAMEDAY_CONFIG:
        logging.error("SAMEDAY_CONFIG nu este setat.")
        return None
        
    creds = settings.SAMEDAY_CONFIG.get(account_key)
    if not creds:
        logging.error(f"Nu s-au găsit credențiale Sameday pentru account_key: {account_key}")
        return None

    url = f"{creds['base_url']}/api/authenticate"
    payload = {"username": creds["username"], "password": creds["password"]}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            token = data.get("token")
            if token:
                sameday_token_cache[account_key] = token
                return token
        except httpx.HTTPStatusError as e:
            logging.error(f"Eroare HTTP la autentificare Sameday pentru {account_key}: {e.response.status_code}")
        except Exception as e:
            logging.error(f"Eroare la autentificare Sameday pentru {account_key}: {e}")
            
    return None

async def track_awb(awb_number: str, account_key: str) -> Optional[TrackingStatus]:
    """
    Interoghează API-ul Sameday pentru a obține starea unui AWB.
    """
    token = await login_sameday(account_key)
    if not token:
        return None

    creds = settings.SAMEDAY_CONFIG.get(account_key)
    url = f"{creds['base_url']}/api/awb/track"
    headers = {"X-Auth-Token": token}
    payload = {"awb": awb_number}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Aici logica de parsare a răspunsului Sameday
            raw_status = data.get("awbStatus", {}).get("statusLabel", "Unknown")
            return TrackingStatus(
                raw_status=raw_status,
                derived_status="unknown" # Va trebui mapat
            )
        except httpx.HTTPStatusError as e:
            logging.error(f"Eroare HTTP la interogarea Sameday pentru AWB {awb_number}: {e.response.status_code}")
        except Exception as e:
            logging.error(f"Eroare la procesarea AWB Sameday {awb_number}: {e}")

    return None

# MODIFICAT: Am redenumit clasa în 'SamedayCourier' și moștenește 'BaseCourier'
class SamedayCourier(BaseCourier):
    async def track(self, awb: str) -> Optional[TrackingStatus]:
        return await track_awb(awb, self.account_key)

    async def create_awb(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logging.warning("Funcționalitatea de creare AWB pentru Sameday nu este implementată.")
        return None