# services/utils.py
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import models
from settings import settings

# --- FUNCȚII NOI ADĂUGATE ---

def _dt(iso_str: Optional[str]) -> Optional[datetime]:
    """Convertește un string ISO 8601 într-un obiect datetime cu fus orar."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None

def map_payment_method(gateways: List[str]) -> str:
    """Map-ează gateway-urile de plată la o metodă simplificată (ex: ramburs, card)."""
    if not gateways or not settings.PAYMENT_MAP:
        return 'unknown'
    
    # Caută o potrivire în mapa de plăți definită în config
    for method, shopify_names in settings.PAYMENT_MAP.items():
        if any(g.lower() in [s.lower() for s in shopify_names] for g in gateways):
            return method
    return 'other'

def courier_from_shopify(tags: List[str]) -> Optional[str]:
    """Extrage numele curierului dintr-o listă de tag-uri ale comenzii."""
    for tag in tags:
        if tag.lower().startswith('courier_'):
            return tag.split('_', 1)[1].lower()
    return None

# --- Funcția ta existentă (NU o șterge) ---

def calculate_and_set_derived_status(order: models.Order):
    """
    Calculează și setează statusul derivat cu o logică îmbunătățită
    pentru statusurile de anulare și refuz.
    """
    now = datetime.now(timezone.utc)
    # Asigură-te că COURIER_STATUS_MAP este încărcat corect în settings
    RAW_STATUS_TO_GROUP_KEY = {}
    if settings.COURIER_STATUS_MAP:
        RAW_STATUS_TO_GROUP_KEY = {
            s.lower().strip(): group
            for group, statuses in settings.COURIER_STATUS_MAP.items()
            for s in statuses
        }
    
    def get_shipment_sort_key(shipment):
        return (shipment.fulfillment_created_at or datetime.min.replace(tzinfo=timezone.utc), shipment.id)

    latest_shipment = max(order.shipments, key=get_shipment_sort_key) if order.shipments else None

    order_tags = {tag.strip().lower() for tag in (order.tags or '').split(',')}
    if 'on-hold' in order_tags or 'hold' in order_tags:
        order.processing_status = "On Hold"
    elif order.address_status == 'invalid':
        order.processing_status = "Adresă Invalidă"
    elif order.address_status == 'nevalidat':
        order.processing_status = "Așteaptă Validare"
    else: 
        if not latest_shipment or not latest_shipment.awb:
             order.processing_status = "Neprocesată"
        else:
             order.processing_status = "Procesată"

    raw_status = (latest_shipment.last_status or 'AWB Generat').strip() if latest_shipment else ''
    courier_status_key = RAW_STATUS_TO_GROUP_KEY.get(raw_status.lower())
    
    is_on_hold = order.is_on_hold_shopify or 'on-hold' in order_tags or 'hold' in order_tags
    is_canceled_event = (order.cancelled_at is not None) or (courier_status_key == 'canceled')
    has_left_warehouse = courier_status_key in ('shipped', 'in_transit', 'pickup_office', 'delivery_issues', 'delivered', 'refused')
    
    new_status = "N/A"

    if is_canceled_event:
        new_status = "❌ Refuzată" if has_left_warehouse else "❌ Anulată"
    elif is_on_hold:
        new_status = "🚦 On Hold"
    elif not latest_shipment or not latest_shipment.awb:
        new_status = "📦 Neprocesată"
    elif courier_status_key == 'delivered':
        new_status = "✅ Livrată"
    elif courier_status_key == 'refused':
        new_status = "❌ Refuzată"
    elif courier_status_key == 'processed':
        if order.fulfilled_at and order.fulfilled_at < (now - timedelta(days=3)):
            new_status = "⏰ Netrimisă (Alertă)"
        else:
            new_status = "✈️ Procesată"
    elif courier_status_key == 'shipped':
        new_status = "🚚 Expediată"
    elif courier_status_key in ('in_transit', 'pickup_office', 'delivery_issues'):
        new_status = "🚚 În curs de livrare"
    else:
        new_status = f"❔ {raw_status}" if raw_status and raw_status != 'AWB Generat' else "✈️ Procesată"
        
    order.derived_status = new_status