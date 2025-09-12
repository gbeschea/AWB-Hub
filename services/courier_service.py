# services/courier_service.py
import asyncio
import logging
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload # Am adăugat selectinload
from tqdm.asyncio import tqdm
import models
from .couriers import get_courier_service
from .couriers.base import TrackingResponse
from settings import settings
from .utils import calculate_and_set_derived_status

async def track_and_update_shipments(db: AsyncSession, full_sync: bool = False):
    logging.info("COURIER SYNC: Preluare AWB-uri de urmărit...")
    
    # --- AICI ESTE MODIFICAREA ---
    # Îi spunem SQLAlchemy să încarce preventiv comanda și TOATE livrările acelei comenzi.
    shipments_query = select(models.Shipment).options(
        joinedload(models.Shipment.order).selectinload(models.Order.shipments)
    )
    # --- SFÂRȘIT MODIFICARE ---
    
    if not full_sync:
        final_statuses_keys = ['delivered', 'refused', 'canceled']
        final_statuses_values = [status for key in final_statuses_keys for status in settings.COURIER_STATUS_MAP.get(key, (None, []))[1]]
        shipments_query = shipments_query.where(
            (models.Shipment.last_status.is_(None)) |
            (models.Shipment.last_status.not_in(final_statuses_values))
        )
    
    shipments_res = await db.execute(shipments_query)
    active_shipments = shipments_res.unique().scalars().all() # Folosim unique() pentru a de-duplica

    if not active_shipments:
        logging.info("COURIER SYNC: Niciun AWB de urmărit.")
        return

    logging.info(f"COURIER SYNC: Se urmăresc {len(active_shipments)} AWB-uri.")

    sameday_shipments = [s for s in active_shipments if 'sameday' in (s.courier or '').lower()]
    other_shipments = [s for s in active_shipments if 'sameday' not in (s.courier or '').lower()]
    
    results: Dict[str, TrackingResponse] = {}
    
    other_sem = asyncio.Semaphore(15)
    async def other_worker(shipment: models.Shipment):
        courier_service = get_courier_service(shipment.courier)
        if not courier_service: return
        async with other_sem:
            response = await courier_service.track_awb(shipment.awb, shipment.account_key)
            results[shipment.awb] = response

    sameday_sem = asyncio.Semaphore(1)
    async def sameday_worker(shipment: models.Shipment):
        courier_service = get_courier_service(shipment.courier)
        if not courier_service: return
        async with sameday_sem:
            await asyncio.sleep(1.0)
            response = await courier_service.track_awb(shipment.awb, shipment.account_key)
            results[shipment.awb] = response
            
    other_tasks = [other_worker(s) for s in other_shipments]
    sameday_tasks = [sameday_worker(s) for s in sameday_shipments]
    
    all_tasks = other_tasks + sameday_tasks
    if all_tasks:
        await tqdm.gather(*all_tasks, desc="Verificare status AWB-uri")

    orders_to_recalculate = set()
    for shipment in active_shipments:
        if response := results.get(shipment.awb):
            shipment.last_status = response.status
            shipment.last_status_at = response.date
            if shipment.order:
                orders_to_recalculate.add(shipment.order)
            
    for order in orders_to_recalculate:
        calculate_and_set_derived_status(order)
        
    await db.commit()
    logging.info(f"COURIER SYNC: Actualizare finalizată pentru {len(results)} AWB-uri.")