# services/courier_service.py

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
    # Funcția map_status rămâne neschimbată
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

# Worker-ul primește serviciul gata creat
async def worker(courier_service, shipment: models.Shipment):
    if not courier_service:
        return None, shipment.id
    try:
        response: TrackingStatus = await courier_service.track(shipment.awb)
        return response, shipment.id
    except Exception as e:
        logging.error(f"Eroare la tracking pentru AWB {shipment.awb}: {e}")
        return None, shipment.id

async def track_and_update_shipments(db: AsyncSession, full_sync: bool = False):
    logging.warning("COURIER SYNC a pornit.")
    final_statuses = ["livrat", "refuzat", "retur"]
    
    query = (
        select(models.Shipment, models.CourierAccount.courier_type, models.CourierAccount.credentials)
        .join(models.CourierAccount, models.Shipment.account_key == models.CourierAccount.account_key)
        .where(or_(
            models.Shipment.derived_status.notin_(final_statuses),
            models.Shipment.derived_status.is_(None)
        ))
    )
    result = await db.execute(query)
    shipments_and_details: List[Tuple[models.Shipment, str, Dict[str, Any]]] = result.all()

    if not shipments_and_details:
        logging.warning("Nu există AWB-uri de urmărit.")
        return

    # --- LOGICA NOUĂ: Creăm o singură instanță de serviciu per cont ---
    service_instances = {}
    all_tasks = []
    
    for shipment, courier_type, credentials in shipments_and_details:
        account_key = shipment.account_key
        if account_key not in service_instances:
            # Creăm serviciul o singură dată pentru fiecare cont
            service_instances[account_key] = get_courier_service(
                courier_type, account_key, credentials
            )
        
        courier_service = service_instances[account_key]
        all_tasks.append(worker(courier_service, shipment))
    # --- SFÂRȘIT LOGICĂ NOUĂ ---

    shipment_map = {sh.id: sh for sh, _, _ in shipments_and_details}
    results = await tqdm.gather(*all_tasks, desc="Verificare status AWB-uri")

    updated_count = 0
    # Despachetarea rezultatului este acum mai simplă
    for response, shipment_id in results:
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