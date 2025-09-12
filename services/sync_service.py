# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/services/sync_service.py

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import joinedload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from settings import settings, ShopifyStore
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

    if settings.PAYMENT_MAP:
        for standard_name, keywords in settings.PAYMENT_MAP.items():
            if not lower_gateways_set.isdisjoint(keywords):
                return standard_name
            if any(keyword in gateway_str_joined for keyword in keywords):
                return standard_name

    if not gateway_str_joined.strip():
        if financial_status == 'paid': return "Fara plata"
        if financial_status == 'pending': return "Ramburs"

    return ", ".join(raw_gateways)

async def courier_from_shopify(db: AsyncSession, tracking_company: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Map a tracking company string to our courier and account keys using the database.
    It first tries an exact match, then falls back to a partial match.
    """
    search_text = (tracking_company or '').strip()
    if not search_text:
        return None, None

    # --- Pasul 1: Caută o potrivire directă (ca înainte) ---
    exact_match_res = await db.execute(
        select(models.CourierMapping).where(models.CourierMapping.shopify_name == search_text)
    )
    exact_mapping = exact_match_res.scalar_one_or_none()

    if exact_mapping:
        acc_res = await db.execute(
            select(models.CourierAccount).where(models.CourierAccount.account_key == exact_mapping.account_key)
        )
        account = acc_res.scalar_one_or_none()
        if account:
            return account.courier_type, account.account_key

    # --- Pasul 2: Fallback la potrivire parțială (LOGICA NOUĂ) ---
    # Preluăm toate conturile active de curier
    all_accounts_res = await db.execute(
        select(models.CourierAccount).where(models.CourierAccount.is_active == True)
    )
    all_accounts = all_accounts_res.scalars().all()

    # Căutăm un cont al cărui 'courier_type' se regăsește în numele de la Shopify
    search_text_lower = search_text.lower()
    for account in all_accounts:
        if account.courier_type.lower() in search_text_lower:
            # Am găsit o potrivire (ex: 'dpd' în 'dpd pixelwave')
            # Returnăm primul cont găsit de acest tip.
            logging.info(f"Potrivire parțială găsită pentru '{search_text}'. Folosim contul: {account.account_key}")
            return account.courier_type, account.account_key

    # Dacă nu am găsit nimic, afișăm avertismentul
    logging.warning(f"Nu s-a găsit nicio mapare (nici directă, nici parțială) pentru curierul: '{search_text}'")
    return None, None


def _get_mapped_address(order_data: Dict[str, Any], pii_source: str) -> Dict[str, Any]:
    """Funcție helper pentru a extrage și mapa adresa PII din diverse surse."""
    address = {}
    
    if pii_source == 'shopify':
        source = order_data.get('shippingAddress')
        if not source:
            return address
        
        first_name = source.get('firstName', '')
        last_name = source.get('lastName', '')
        
        address = {
            'name': f"{first_name} {last_name}".strip(),
            'address1': source.get('address1'),
            'address2': source.get('address2'),
            'phone': source.get('phone'),
            'city': source.get('city'),
            'zip': source.get('zip'),
            'province': source.get('province'),
            'country': source.get('country'),
            'email': order_data.get('email')
        }

    elif pii_source == 'metafield':
        source_node = order_data.get('metafield')
        if not source_node or not source_node.get('value'):
            return address
        
        try:
            metafield_data = json.loads(source_node['value'])
            address = {
                'name': f"{metafield_data.get('first_name', '')} {metafield_data.get('last_name', '')}".strip(),
                'address1': metafield_data.get('address1'),
                'address2': metafield_data.get('address2'),
                'phone': metafield_data.get('phone_number'),
                'city': metafield_data.get('city'),
                'zip': metafield_data.get('postal_code'),
                'province': metafield_data.get('county'),
                'country': metafield_data.get('country'),
                'email': metafield_data.get('email')
            }
        except json.JSONDecodeError:
            logging.warning(f"Nu s-a putut decoda metafield-ul PII pentru comanda {order_data.get('name')}")

    return address

async def run_orders_sync(db: AsyncSession, days: int, full_sync: bool = False):
    start_ts = datetime.now(timezone.utc)
    sync_type = "TOTALĂ" if full_sync else "STANDARD"
    logging.warning(f"ORDER SYNC ({sync_type}) a pornit pentru ultimele {days} zile.")
    await manager.broadcast({"type": "sync_start", "message": f"Sincronizare comenzi ({sync_type})...", "sync_type": "orders"})

    stores_from_db_res = await db.execute(select(models.Store).where(models.Store.is_active == True))
    stores_from_db = stores_from_db_res.scalars().all()

    if not stores_from_db:
        logging.warning("ORDER SYNC: Nu există magazine active în baza de date. Sincronizarea a fost oprită.")
        await manager.broadcast({"type": "sync_end", "message": "Nu sunt magazine active pentru sincronizare."})
        return

    stores_to_sync = [
        ShopifyStore(
            brand=db_store.name,
            domain=db_store.domain,
            shared_secret=db_store.shared_secret,
            access_token=db_store.access_token,
            pii_source=db_store.pii_source,
            api_version="2025-07"
        ) for db_store in stores_from_db
    ]
    
    fetch_tasks = [shopify_service.fetch_orders(s, since_days=days) for s in stores_to_sync]
    all_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    existing_stores_res = await db.execute(select(models.Store))
    existing_stores = {st.domain: st for st in existing_stores_res.scalars().all()}

    total_orders_to_process = sum(len(res) for res in all_results if isinstance(res, list))
    await manager.broadcast({"type": "progress_update", "current": 0, "total": total_orders_to_process, "message": f"S-au găsit {total_orders_to_process} comenzi. Se procesează..."})

    processed_count = 0
    all_processed_order_ids = set()

    for s, orders_or_exception in zip(stores_to_sync, all_results):
        if isinstance(orders_or_exception, Exception):
            logging.warning(f"Eroare la preluarea comenzilor pentru {s.domain}: {orders_or_exception}")
            continue

        store_rec = existing_stores.get(s.domain)
        if not store_rec:
            logging.warning(f"ORDER SYNC: Magazinul '{s.brand}' ({s.domain}) nu a fost găsit în BD, deși a fost sincronizat. Se adaugă automat.")
            store_rec = models.Store(name=s.brand, domain=s.domain)
            db.add(store_rec)
            await db.flush()
            existing_stores[s.domain] = store_rec

        for o in orders_or_exception:
            sid = o['id']
            order_res = await db.execute(select(models.Order).options(joinedload('*')).where(models.Order.shopify_order_id == sid))
            order = order_res.unique().scalar_one_or_none()

            shipping_address = _get_mapped_address(o, store_rec.pii_source)
            if not shipping_address:
                 logging.warning(f"Nu s-au găsit date PII pentru comanda {o.get('name')} din sursa '{store_rec.pii_source}'")

            gateways = o.get('paymentGatewayNames', [])
            financial_status = o.get('displayFinancialStatus', 'unknown')
            mapped_payment = map_payment_method(gateways, financial_status)
            total_price_str = o.get('totalPriceSet', {}).get('shopMoney', {}).get('amount', '0.0')

            status_from_shopify = (o.get('displayFulfillmentStatus') or 'unfulfilled').strip().lower()
            if status_from_shopify == 'success':
                status_from_shopify = 'fulfilled'

            fulfillment_orders = o.get('fulfillmentOrders', {}).get('edges', [])
            has_active_hold = any(ff_edge.get('node', {}).get('fulfillmentHolds') for ff_edge in fulfillment_orders)

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
                    
                    fulfillment_date = _dt(f.get('createdAt'))
                    # Mai întâi, apelăm funcția și obținem cheia contului
                    courier_type, account_key = await courier_from_shopify(db, tracking_info.get('company', ''))

                    # Căutăm dacă există deja o înregistrare
                    shipment_res = await db.execute(select(models.Shipment).where(models.Shipment.awb == awb))
                    sh = shipment_res.scalar_one_or_none()

                    # AICI ESTE CORECȚIA COMPLETĂ
                    if not sh:
                        # Dacă NU există, adăugăm una nouă folosind 'account_key'
                        db.add(models.Shipment(order_id=order.id, awb=awb, courier=account_key, account_key=account_key, shopify_fulfillment_id=str(f.get('id')), fulfillment_created_at=fulfillment_date))
                    else:
                        # Dacă există, o actualizăm folosind tot 'account_key'
                        sh.courier = account_key
                        sh.account_key = account_key
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
    """Rulează o sincronizare completă: comenzi și apoi curieri."""
    await run_orders_sync(db, days, full_sync=True)
    await run_couriers_sync(db, full_sync=True)