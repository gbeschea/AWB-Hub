import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.orm import joinedload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from settings import settings
from . import shopify_service, address_service, courier_service
from .utils import calculate_and_set_derived_status
from websocket_manager import manager

def _dt(v: Optional[str]) -> Optional[datetime]:
    if not v: return None
    try:
        return datetime.fromisoformat(v.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None

def map_payment_method(gateways: List[str], financial_status: str) -> str:
    raw_gateways = gateways or []
    lower_gateways_set = {g.lower().strip() for g in raw_gateways}
    gateway_str_joined = ", ".join(raw_gateways).lower()

    for standard_name, keywords in settings.PAYMENT_MAP.items():
        if not lower_gateways_set.isdisjoint(keywords):
            return standard_name
        if any(keyword in gateway_str_joined for keyword in keywords):
            return standard_name

    if not gateway_str_joined.strip():
        if financial_status == 'paid': return "Fara plata"
        if financial_status == 'pending': return "Ramburs"

    return ", ".join(raw_gateways)

def courier_from_shopify(tracking_company: str, tracking_url: str) -> str:
    search_text = (tracking_company or '').strip().lower()
    if not search_text:
        return "unknown"
    
    sorted_courier_keys = sorted(settings.COURIER_MAP.keys(), key=len, reverse=True)

    for key in sorted_courier_keys:
        if key.lower() in search_text:
            return settings.COURIER_MAP[key]
            
    logging.warning(f"Nu s-a putut mapa curierul pentru '{tracking_company}'.")
    return tracking_company


async def run_orders_sync(db: AsyncSession, days: int, full_sync: bool = False):
    start_ts = datetime.now(timezone.utc)
    sync_type = "TOTALĂ" if full_sync else "STANDARD"
    logging.warning(f"ORDER SYNC ({sync_type}) a pornit pentru ultimele {days} zile.")
    await manager.broadcast({"type": "sync_start", "message": f"Sincronizare comenzi ({sync_type})...", "sync_type": "orders"})

    fetch_tasks = [shopify_service.fetch_orders(s, since_days=days) for s in settings.SHOPIFY_STORES]
    all_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    existing_stores_res = await db.execute(select(models.Store))
    existing_stores = {st.domain: st for st in existing_stores_res.scalars().all()}

    total_orders_to_process = sum(len(res) for res in all_results if isinstance(res, list))
    await manager.broadcast({"type": "progress_update", "current": 0, "total": total_orders_to_process, "message": f"S-au găsit {total_orders_to_process} comenzi. Se procesează..."})

    processed_count = 0
    all_processed_order_ids = set()

    for s, orders_or_exception in zip(settings.SHOPIFY_STORES, all_results):
        if isinstance(orders_or_exception, Exception):
            logging.warning(f"Eroare la preluarea comenzilor pentru {s.domain}: {orders_or_exception}")
            continue

        store_rec = existing_stores.get(s.domain)
        if not store_rec:
            logging.warning(f"ORDER SYNC: Magazinul '{s.brand}' ({s.domain}) nu a fost găsit în BD. Se adaugă automat.")
            store_rec = models.Store(name=s.brand, domain=s.domain)
            db.add(store_rec)
            await db.flush()
            existing_stores[s.domain] = store_rec

        for o in orders_or_exception:
            sid = o['id']
            order_res = await db.execute(select(models.Order).options(joinedload('*')).where(models.Order.shopify_order_id == sid))
            order = order_res.unique().scalar_one_or_none()

            gateways = o.get('paymentGatewayNames', [])
            financial_status = o.get('displayFinancialStatus', 'unknown')
            mapped_payment = map_payment_method(gateways, financial_status)
            total_price_str = o.get('totalPriceSet', {}).get('shopMoney', {}).get('amount', '0.0')

            shipping_address = o.get('shippingAddress') or {}

            status_from_shopify = (o.get('displayFulfillmentStatus') or 'unfulfilled').strip().lower()
            if status_from_shopify == 'success':
                status_from_shopify = 'fulfilled'

            fulfillment_orders = o.get('fulfillmentOrders', {}).get('edges', [])
            has_active_hold = False
            if fulfillment_orders:
                for ff_edge in fulfillment_orders:
                    holds = ff_edge.get('node', {}).get('fulfillmentHolds', [])
                    if holds:
                        has_active_hold = True
                        break

            order_data = {
                'name': o.get('name'),
                'customer': shipping_address.get('name') or 'N/A',
                'created_at': _dt(o.get('createdAt')),
                'cancelled_at': _dt(o.get('cancelledAt')),
                'is_on_hold_shopify': has_active_hold,
                'financial_status': financial_status,
                'total_price': float(total_price_str) if total_price_str else 0.0,
                'payment_gateway_names': ", ".join(gateways),
                'mapped_payment': mapped_payment,
                'tags': ",".join(o.get('tags', [])),
                'note': o.get('note', ''),
                'shopify_status': status_from_shopify,
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
                order = models.Order(store_id=store_rec.id, shopify_order_id=sid, **order_data)
                db.add(order)
                await db.flush()
                line_items_data = o.get('lineItems', {}).get('edges', [])
                for li_edge in line_items_data:
                    li = li_edge['node']
                    db.add(models.LineItem(order_id=order.id, sku=li.get('sku'), title=li.get('title'), quantity=li.get('quantity')))
            else:
                for key, value in order_data.items():
                    setattr(order, key, value)

            ffs = o.get('fulfillments', [])
            if ffs:
                for f in ffs:
                    tracking_info_list = f.get('trackingInfo', [])
                    if not tracking_info_list:
                        continue
                    tracking_info = tracking_info_list[0]
                    awb = str(tracking_info.get('number', '')).strip()
                    if not awb: continue

                    # --- START CORECȚIE ---
                    # Definim variabila aici, la începutul buclei
                    fulfillment_date = _dt(f.get('createdAt'))
                    # --- FINAL CORECȚIE ---

                    courier_key = courier_from_shopify(tracking_info.get('company', ''), tracking_info.get('url', ''))

                    shipment_res = await db.execute(select(models.Shipment).where(models.Shipment.awb == awb))
                    sh = shipment_res.scalar_one_or_none()
                    if not sh:
                        db.add(models.Shipment(order_id=order.id, awb=awb, courier=courier_key, account_key=courier_key, shopify_fulfillment_id=str(f.get('id')), fulfillment_created_at=fulfillment_date))
                    else:
                        sh.courier = courier_key
                        sh.account_key = courier_key
                        sh.fulfillment_created_at = fulfillment_date

            all_processed_order_ids.add(order.id)
            processed_count += 1
            if processed_count % 50 == 0:
                await manager.broadcast({"type": "progress_update", "current": processed_count, "total": total_orders_to_process, "message": f"Se procesează... ({processed_count}/{total_orders_to_process})"})

    await db.commit()

    if all_processed_order_ids:
        logging.warning(f"Validare adrese și recalculare statusuri pentru {len(all_processed_order_ids)} comenzi...")
        orders_to_recalc_res = await db.execute(select(models.Order).options(joinedload(models.Order.shipments)).where(models.Order.id.in_(all_processed_order_ids)))
        orders_to_recalc = orders_to_recalc_res.unique().scalars().all()
        for order in orders_to_recalc:
            if order.address_status != 'valid':
                await address_service.validate_address_for_order(db, order)
            calculate_and_set_derived_status(order)

    await db.commit()
    await manager.broadcast({"type": "sync_end", "message": f"Sincronizare finalizată! {processed_count} comenzi actualizate."})
    logging.warning(f"ORDER SYNC finalizat în {(datetime.now(timezone.utc) - start_ts).total_seconds():.1f}s.")

    

async def run_couriers_sync(db: AsyncSession, full_sync: bool = False):
    await courier_service.track_and_update_shipments(db, full_sync=full_sync)

async def run_full_sync(db: AsyncSession, days: int):
    await run_orders_sync(db, days, full_sync=True)
    await run_couriers_sync(db, full_sync=True)

