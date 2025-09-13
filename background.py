# background.py
import asyncio
import logging
from typing import List
from sqlalchemy.orm import joinedload
from sqlalchemy import select

import models
# --- MODIFICARE: Am adăugat importurile necesare ---
from services import sync_service, courier_service
from settings import settings
from database import AsyncSessionLocal

# --- Funcția ta existentă (NU o șterge) ---
async def _do_update_work(session, awb_list: List[str]):
    """Funcția care conține logica efectivă, primind o sesiune validă."""
    # ... (codul tău existent aici) ...
    shipments_result = await session.execute(
        select(models.Shipment)
        .options(
            joinedload(models.Shipment.order).joinedload(models.Order.store)
        )
        .where(models.Shipment.awb.in_(awb_list))
    )
    shipments = shipments_result.unique().scalars().all()

    store_configs = {s.domain: s for s in settings.SHOPIFY_STORES}
    # Asigură-te că ai COURIER_MAP în settings.py
    courier_display_names = {v: k for k, v in getattr(settings, 'COURIER_MAP', {}).items()}
    update_tasks = []

    for ship in shipments:
        if not (ship.order and ship.order.store and ship.order.shopify_order_id):
            continue
        store_cfg = store_configs.get(ship.order.store.domain)
        if not store_cfg:
            continue

        tracking_url = f"https://sameday.ro/track-awb/{ship.awb}" if 'sameday' in (ship.courier or '').lower() else f"https://tracking.dpd.ro?shipmentNumber={ship.awb}"
        tracking_info = {
            "company": courier_display_names.get(ship.courier, ship.courier),
            "number": ship.awb,
            "url": tracking_url
        }
        order_gid = f"gid://shopify/Order/{ship.order.shopify_order_id}"

        # Presupunem că ai o funcție `notify_shopify_of_shipment` în shopify_service
        from services import shopify_service
        task = shopify_service.notify_shopify_of_shipment(
            store_cfg=store_cfg,
            order_gid=order_gid,
            fulfillment_id=ship.shopify_fulfillment_id,
            tracking_info=tracking_info
        )
        update_tasks.append(task)

    if update_tasks:
        await asyncio.gather(*update_tasks)


async def update_shopify_in_background(awb_list: List[str]):
    """Wrapper-ul care creează o sesiune nouă pentru task-ul de fundal."""
    logging.info(f"Background task pornit pentru a notifica Shopify pentru {len(awb_list)} AWB-uri.")
    async with AsyncSessionLocal() as session:
        try:
            await _do_update_work(session, awb_list)
            await session.commit()
        except Exception as e:
            logging.error(f"Eroare în task-ul de fundal Shopify: {e}", exc_info=True)
            await session.rollback()
    logging.info(f"✅ Notificarea Shopify pentru {len(awb_list)} expedieri a fost finalizată.")


# --- NOUL COD PENTRU TASK-URI PERIODICE ---

async def run_periodic_task(interval_minutes: int, task_function, task_name: str):
    """Rulează o funcție la un interval specificat de minute."""
    logging.info(f"Task-ul periodic '{task_name}' a fost pornit. Se va rula la fiecare {interval_minutes} minute.")
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await task_function(session)
                await session.commit()
        except Exception as e:
            logging.error(f"Eroare în task-ul periodic '{task_name}': {e}", exc_info=True)
        
        await asyncio.sleep(interval_minutes * 60)

def start_background_tasks():
    """
    Creează și pornește task-urile de fundal pentru sincronizări.
    Aceasta este funcția pe care o caută main.py.
    """
    logging.info("Se inițializează task-urile de fundal...")
    
    # Task pentru sincronizarea comenzilor Shopify
    asyncio.create_task(run_periodic_task(
        interval_minutes=settings.SYNC_INTERVAL_ORDERS_MINUTES,
        task_function=sync_service.sync_orders,
        task_name="Sincronizare Comenzi Shopify"
    ))

    # Task pentru actualizarea statusului la curieri
    asyncio.create_task(run_periodic_task(
        interval_minutes=settings.SYNC_INTERVAL_COURIERS_MINUTES,
        task_function=courier_service.track_and_update_shipments,
        task_name="Actualizare Status Curieri"
    ))