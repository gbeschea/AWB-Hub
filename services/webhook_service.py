import logging
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
import models
from services.sync_service import _dt, map_payment_method, courier_from_shopify
from services.utils import calculate_and_set_derived_status
from services.address_service import validate_address_for_order

async def _create_or_update_order(db: AsyncSession, store_id: int, payload: Dict[str, Any]):
    """Creează sau actualizează o comandă și produsele asociate pe baza datelor de la webhook."""
    shopify_id = str(payload['id'])
    
    order_res = await db.execute(
        select(models.Order)
        .options(joinedload(models.Order.line_items), joinedload(models.Order.shipments))
        .where(models.Order.shopify_order_id == shopify_id)
    )
    order = order_res.unique().scalar_one_or_none()

    shipping_address = payload.get('shipping_address') or {}
    total_price_str = payload.get('total_price_set', {}).get('shop_money', {}).get('amount', '0.0')

    order_data = {
        'name': payload.get('name'),
        'customer': shipping_address.get('name') or 'N/A',
        'created_at': _dt(payload.get('created_at')),
        'updated_at': _dt(payload.get('updated_at')),
        'cancelled_at': _dt(payload.get('cancelled_at')),
        'financial_status': payload.get('financial_status', 'unknown'),
        'total_price': float(total_price_str) if total_price_str else 0.0,
        'payment_gateway_names': ", ".join(payload.get('payment_gateway_names', [])),
        'mapped_payment': map_payment_method(payload.get('payment_gateway_names', []), payload.get('financial_status', 'unknown')),
        'tags': ",".join(payload.get('tags', [])),
        'note': payload.get('note', ''),
        'shopify_status': (payload.get('fulfillment_status') or 'unfulfilled').strip().lower(),
        'shipping_name': shipping_address.get('name'),
        'shipping_address1': shipping_address.get('address1'),
        'shipping_address2': shipping_address.get('address2'),
        'shipping_phone': shipping_address.get('phone'),
        'shipping_city': shipping_address.get('city'),
        'shipping_zip': shipping_address.get('zip'),
        'shipping_province': shipping_address.get('province'),
        'shipping_country': shipping_address.get('country'),
    }

    if not order:
        order = models.Order(store_id=store_id, shopify_order_id=shopify_id, **order_data)
        db.add(order)
        await db.flush() # Pentru a obține ID-ul comenzii
    else:
        for key, value in order_data.items():
            setattr(order, key, value)
    
    # Actualizează produsele
    db_line_items = {li.id: li for li in order.line_items}
    payload_line_items = {li['id']: li for li in payload.get('line_items', [])}
    
    for li_id, li_data in payload_line_items.items():
        if li_id in db_line_items:
            db_line_items[li_id].quantity = li_data['quantity']
            db_line_items[li_id].price = li_data['price']
        else:
            db.add(models.LineItem(order_id=order.id, sku=li_data.get('sku'), title=li_data.get('title'), quantity=li_data.get('quantity')))

    # Șterge produsele care nu mai sunt în comandă
    for li_id, li_db in db_line_items.items():
        if li_id not in payload_line_items:
            await db.delete(li_db)
            
    await validate_address_for_order(db, order)
    calculate_and_set_derived_status(order)
    await db.commit()
    logging.warning(f"Webhook: Comanda '{order.name}' a fost creată/actualizată.")

async def _delete_order(db: AsyncSession, payload: Dict[str, Any]):
    """Șterge o comandă din baza de date."""
    shopify_id = str(payload['id'])
    order_res = await db.execute(select(models.Order).where(models.Order.shopify_order_id == shopify_id))
    order = order_res.scalar_one_or_none()
    if order:
        await db.delete(order)
        await db.commit()
        logging.warning(f"Webhook: Comanda cu Shopify ID '{shopify_id}' a fost ștearsă.")

async def _process_fulfillment(db: AsyncSession, payload: Dict[str, Any]):
    """Procesează un eveniment de creare/actualizare fulfillment."""
    order_shopify_id = str(payload['order_id'])
    order_res = await db.execute(select(models.Order).options(joinedload(models.Order.shipments)).where(models.Order.shopify_order_id == order_shopify_id))
    order = order_res.unique().scalar_one_or_none()
    if not order:
        logging.warning(f"Webhook: Comanda cu Shopify ID '{order_shopify_id}' nu a fost găsită pentru fulfillment.")
        return

    awb = str(payload.get('tracking_number', '')).strip()
    if not awb: return

    courier_key = courier_from_shopify(payload.get('tracking_company', ''), payload.get('tracking_url', ''))
    
    shipment = next((s for s in order.shipments if s.awb == awb), None)
    
    if not shipment:
        shipment = models.Shipment(
            order_id=order.id,
            awb=awb,
            courier=courier_key,
            account_key=courier_key,
            shopify_fulfillment_id=str(payload.get('id')),
            fulfillment_created_at=_dt(payload.get('created_at'))
        )
        db.add(shipment)
    else:
        shipment.courier = courier_key
        shipment.account_key = courier_key
        shipment.fulfillment_created_at = _dt(payload.get('created_at'))

    calculate_and_set_derived_status(order)
    await db.commit()
    logging.warning(f"Webhook: Fulfillment pentru comanda '{order.name}' a fost procesat.")


# Dicționarul principal care mapează topicurile la funcțiile de procesare
WEBHOOK_HANDLERS = {
    "orders/create": _create_or_update_order,
    "orders/updated": _create_or_update_order,
    "orders/edited": _create_or_update_order,
    "orders/delete": _delete_order,
    "fulfillments/create": _process_fulfillment,
    "fulfillments/update": _process_fulfillment,
}

async def process_webhook_event(db: AsyncSession, topic: str, store_id: int, payload: Dict[str, Any]):
    """Funcția principală care primește și routează evenimentele de la webhook."""
    handler = WEBHOOK_HANDLERS.get(topic)
    if handler:
        await handler(db, store_id, payload)
    else:
        logging.info(f"Webhook: Niciun handler găsit pentru topicul '{topic}'.")
