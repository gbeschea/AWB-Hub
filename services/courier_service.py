import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from tqdm.asyncio import tqdm
from typing import List, Tuple, Dict, Any

import models
from settings import settings
from .couriers.common import TrackingStatus
from .couriers import get_courier_service

def map_status(raw_status: str, account_key: str) -> str:
    raw_status_lower = raw_status.lower().strip()
    courier_name = account_key.lower() if account_key else ''
    if settings.COURIER_STATUS_MAP:
        courier_map = settings.COURIER_STATUS_MAP.get(courier_name, {})
        for derived, raw_list in courier_map.items():
            if any(keyword.lower() in raw_status_lower for keyword in raw_list):
                return derived
    if "livrat" in raw_status_lower or "delivered" in raw_status_lower: return "livrat"
    if "refuzat" in raw_status_lower or "refused" in raw_status_lower: return "refuzat"
    if "retur" in raw_status_lower or "return" in raw_status_lower: return "retur"
    return "in_tranzit"

# MODIFICARE: Am redenumit parametrul în 'courier_credentials' pentru claritate
async def other_worker(shipment: models.Shipment, courier_type: str, courier_credentials: Dict[str, Any]):
    """Worker function to track a single AWB."""
    # Trimitem 'courier_credentials' mai departe
    courier_service = get_courier_service(courier_type, shipment.account_key, courier_credentials)
    if not courier_service:
        logging.warning(f"Nu s-a găsit/putut crea serviciu de curierat pentru tipul '{courier_type}' (AWB: {shipment.awb})")
        return None, shipment.id, courier_type
    try:
        response: TrackingStatus = await courier_service.track(shipment.awb)
        return response, shipment.id, courier_type
    except Exception as e:
        logging.error(f"Eroare la tracking pentru AWB {shipment.awb} ({courier_type}): {e}")
        return None, shipment.id, courier_type

async def track_and_update_shipments(db: AsyncSession, full_sync: bool = False):
    """Tracks all non-final shipments and updates their status in the database."""
    logging.warning("COURIER SYNC a pornit.")
    final_statuses = ["livrat", "refuzat", "retur"]
    
    # MODIFICARE: Folosim 'credentials' în loc de 'settings'
    query = (
        select(models.Shipment, models.CourierAccount.courier_type, models.CourierAccount.credentials)
        .join(models.CourierAccount, models.Shipment.account_key == models.CourierAccount.account_key)
        .where(or_(
            models.Shipment.derived_status.notin_(final_statuses),
            models.Shipment.derived_status.is_(None)
        ))
    )
    if not full_sync: pass

    result = await db.execute(query)
    shipments_and_details: List[Tuple[models.Shipment, str, Dict[str, Any]]] = result.all()

    if not shipments_and_details:
        logging.warning("Nu există AWB-uri de urmărit.")
        return

    all_tasks = [other_worker(sh, c_type, c_credentials) for sh, c_type, c_credentials in shipments_and_details]
    shipment_map = {sh.id: sh for sh, _, _ in shipments_and_details}
    results = await tqdm.gather(*all_tasks, desc="Verificare status AWB-uri")

    updated_count = 0
    for response, shipment_id, courier_type in results:
        if response and shipment_id:
            shipment = shipment_map.get(shipment_id)
            if shipment:
                derived_status = map_status(response.raw_status, shipment.account_key)
                shipment.last_status = response.raw_status
                shipment.derived_status = derived_status
                updated_count += 1

    if updated_count > 0:
        await db.commit()
        logging.warning(f"S-au actualizat {updated_count} statusuri de AWB-uri.")
    else:
        logging.warning("Nu s-a actualizat niciun status de AWB.")