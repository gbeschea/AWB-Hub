from datetime import datetime, timezone, timedelta
import models  # Asigură-te că acest import este aici
from settings import settings

def calculate_and_set_derived_status(order: models.Order):
    """
    Calculează și setează statusul derivat cu o logică îmbunătățită
    pentru statusurile de anulare și refuz.
    """
    now = datetime.now(timezone.utc)
    RAW_STATUS_TO_GROUP_KEY = {s.lower().strip(): group for group, (_, statuses) in settings.COURIER_STATUS_MAP.items() for s in statuses}
    
    def get_shipment_sort_key(shipment):
        # Prioritizează data, apoi ID-ul. None este tratat ca o dată foarte veche.
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