# services/sync_service.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import List, Dict, Any

import models
from services import shopify_service
from settings import settings, ShopifyStore

async def process_and_save_orders(db: AsyncSession, store: models.Store, fetched_orders: List[Dict[str, Any]]):
    """Procesează și salvează o listă de comenzi de la Shopify în baza de date locală."""
    shopify_order_ids = [o['id'] for o in fetched_orders]
    if not shopify_order_ids:
        return

    existing_orders_res = await db.execute(
        select(models.Order).where(models.Order.shopify_order_id.in_(shopify_order_ids))
    )
    existing_orders_map = {o.shopify_order_id: o for o in existing_orders_res.scalars()}

    for order_data in fetched_orders:
        order_id_gid = order_data['id']
        order = existing_orders_map.get(order_id_gid)

        if not order:
            order = models.Order(store_id=store.id, shopify_order_id=order_id_gid)
            db.add(order)
        
        # Actualizează câmpurile comenzii cu datele de la Shopify
        order.name = order_data.get('name')
        order.created_at = datetime.fromisoformat(order_data['createdAt']) if order_data.get('createdAt') else None
        order.cancelled_at = datetime.fromisoformat(order_data['cancelledAt']) if order_data.get('cancelledAt') else None
        order.financial_status = order_data.get('displayFinancialStatus')
        order.shopify_status = order_data.get('displayFulfillmentStatus')
        order.total_price = float(order_data.get('totalPriceSet', {}).get('shopMoney', {}).get('amount', 0.0))
        order.tags = ", ".join(order_data.get('tags', []))
        order.note = order_data.get('note')
        
        # Date personale (dacă sunt disponibile)
        if 'shippingAddress' in order_data and order_data['shippingAddress']:
            shipping = order_data['shippingAddress']
            order.shipping_name = f"{shipping.get('firstName', '')} {shipping.get('lastName', '')}".strip()
            order.shipping_address1 = shipping.get('address1')
            order.shipping_address2 = shipping.get('address2')
            order.shipping_city = shipping.get('city')
            order.shipping_province = shipping.get('province')
            order.shipping_zip = shipping.get('zip')
            order.shipping_country = shipping.get('country')
            order.shipping_phone = shipping.get('phone')
            
    logging.info(f"Procesate {len(fetched_orders)} comenzi pentru magazinul {store.name}.")
async def sync_orders(db: AsyncSession):
    """
    Sincronizează comenzile de la toate magazinele Shopify active din baza de date.
    """
    logging.info("A pornit sincronizarea comenzilor Shopify...")
    
    stores_res = await db.execute(select(models.Store).where(models.Store.is_active == True))
    active_stores = stores_res.scalars().all()

    if not active_stores:
        logging.warning("Niciun magazin activ găsit pentru sincronizare.")
        return

    for store_from_db in active_stores:
        # Creăm dinamic obiectul de configurare din datele din DB
        store_config = ShopifyStore(
            brand=store_from_db.name,
            domain=store_from_db.domain,
            access_token=store_from_db.access_token,
            pii_source=store_from_db.pii_source,
            shared_secret=store_from_db.shared_secret
        )
        
        try:
            logging.info(f"Se preiau comenzile pentru magazinul: {store_from_db.name}...")
            fetched_orders = await shopify_service.fetch_orders(store_config, since_days=7)
            
            if fetched_orders:
                await process_and_save_orders(db, store_from_db, fetched_orders)
            
            store_from_db.last_sync_at = datetime.now(timezone.utc)

        except Exception as e:
            logging.error(f"Eroare la sincronizarea magazinului {store_from_db.name}: {e}", exc_info=True)
            await db.rollback()

    logging.info("Sincronizarea comenzilor Shopify a fost finalizată.")

