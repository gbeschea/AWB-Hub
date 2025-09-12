# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/services/courier_service.py

import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from tqdm.asyncio import tqdm
from typing import List

import models
from settings import settings
# MODIFICAT: Am schimbat 'TrackingResponse' în 'TrackingStatus'
from .couriers.base import TrackingStatus
from .couriers import get_courier_service

def map_status(raw_status: str, courier: str) -> str:
    """Map a raw courier status to a derived, standardized status."""
    raw_status_lower = raw_status.lower().strip()
    
    if settings.COURIER_STATUS_MAP:
        courier_map = settings.COURIER_STATUS_MAP.get(courier, {})
        for derived, raw_list in courier_map.items():
            if any(keyword.lower() in raw_status_lower for keyword in raw_list):
                return derived
                
    # Fallback if no mapping is found
    if "livrat" in raw_status_lower or "delivered" in raw_status_lower:
        return "livrat"
    if "refuzat" in raw_status_lower or "refused" in raw_status_lower:
        return "refuzat"
    if "retur" in raw_status_lower or "return" in raw_status_lower:
        return "retur"
        
    return "in_tranzit"

async def other_worker(shipment: models.Shipment):
    """Worker function to track a single AWB."""
    courier_service = get_courier_service(shipment.courier, shipment.account_key)
    if not courier_service:
        logging.warning(f"Nu s-a găsit serviciu de curierat pentru {shipment.courier}")
        return None, shipment.id

    try:
        response: TrackingStatus = await courier_service.track(shipment.awb)
        return response, shipment.id
    except Exception as e:
        logging.error(f"Eroare la tracking pentru AWB {shipment.awb} ({shipment.courier}): {e}")
        return None, shipment.id

async def track_and_update_shipments(db: AsyncSession, full_sync: bool = False):
    """Tracks all non-final shipments and updates their status in the database."""
    logging.warning("COURIER SYNC a pornit.")
    
    final_statuses = ["livrat", "refuzat", "retur"]
    query = select(models.Shipment).where(or_(
        models.Shipment.derived_status.notin_(final_statuses),
        models.Shipment.derived_status.is_(None)
    ))
    
    if not full_sync:
        # Adaugă condiții suplimentare pentru sync parțial dacă este necesar
        pass

    result = await db.execute(query)
    shipments_to_track: List[models.Shipment] = result.scalars().all()

    if not shipments_to_track:
        logging.warning("Nu există AWB-uri de urmărit.")
        return

    all_tasks = [other_worker(sh) for sh in shipments_to_track]
    
    shipment_map = {sh.id: sh for sh in shipments_to_track}
    
    results = await tqdm.gather(*all_tasks, desc="Verificare status AWB-uri")

    updated_count = 0
    for response, shipment_id in results:
        if response and shipment_id:
            shipment = shipment_map.get(shipment_id)
            if shipment:
                derived_status = map_status(response.raw_status, shipment.courier)
                shipment.last_status = response.raw_status
                shipment.derived_status = derived_status
                # shipment.last_status_at = ... # Ar trebui adăugat și data statusului
                updated_count += 1

    if updated_count > 0:
        await db.commit()
        logging.warning(f"S-au actualizat {updated_count} statusuri de AWB-uri.")
    else:
        logging.warning("Nu s-a actualizat niciun status de AWB.")