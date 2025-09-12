# background.py
import asyncio
import logging
from typing import List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

import models
from services import shopify_service
from config import SHOPIFY_STORES, COURIER_MAP

async def update_shopify_in_background(db: Session, awb_list: List[str]):
    """Notifică Shopify despre AWB-urile procesate."""
    shipments = db.execute(select(models.Shipment).options(joinedload(models.Shipment.order).joinedload(models.Order.store)).where(models.Shipment.awb.in_(awb_list))).unique().scalars().all()
    store_configs = {s['domain']: s for s in SHOPIFY_STORES}
    courier_display_names = {v: k for k, v in COURIER_MAP.items()}
    update_tasks = []
    for ship in shipments:
        if not (ship.order and ship.order.store and ship.order.shopify_order_id and ship.shopify_fulfillment_id): continue
        if not (store_cfg := store_configs.get(ship.order.store.domain)): continue
        tracking_url = f"https://sameday.ro/track-awb/{ship.awb}" if 'sameday' in (ship.courier or '').lower() else f"https://tracking.dpd.ro?shipmentNumber={ship.awb}"
        tracking_info = {"company": courier_display_names.get(ship.courier, ship.courier), "number": ship.awb, "url": tracking_url}
        task = shopify_service.notify_shopify_of_shipment(store_cfg=store_cfg, order_gid=f"gid://shopify/Order/{ship.order.shopify_order_id}", fulfillment_id=ship.shopify_fulfillment_id, tracking_info=tracking_info)
        update_tasks.append(task)
    if update_tasks:
        await asyncio.gather(*update_tasks)
    logging.info(f"✅ Notificarea Shopify pentru {len(awb_list)} expedieri a fost finalizată.")