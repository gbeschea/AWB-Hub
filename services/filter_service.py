# services/filter_service.py

from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select
from sqlalchemy import select, and_, or_, func, desc, asc, table, column
from sqlalchemy.dialects.postgresql import json_agg
import models
from settings import settings

# --- Helper Functions ---

def get_orders_view():
    """Definește coloanele necesare din view-ul de comenzi."""
    return table(
        "orders_with_derived_status",
        column("id"), column("store_id"), column("name"), column("customer"),
        column("created_at"), column("fulfilled_at"), column("address_status"),
        column("financial_status"), column("shopify_status"), column("derived_status"),
        column("total_price"), column("tags"), column("shipping_city"), column("shipping_country")
    )

def get_shipments_view():
    """Definește coloanele necesare din view-ul de expedieri."""
    return table(
        "shipments_with_derived_status",
        column("id"), column("order_id"), column("courier"), column("awb"),
        column("printed_at"), column("last_status"), 
        # Adăugăm un alias pentru a nu intra în conflict cu derived_status din comenzi
        column("derived_status").label("shipment_derived_status") 
    )

async def apply_filters_and_get_orders(db: AsyncSession, **kwargs) -> Tuple[List[Dict[str, Any]], int]:
    """
    Preia, filtrează, sortează și paginează comenzile într-o singură interogare,
    returnând un dicționar de date gata pentru a fi trimis la template.
    """
    page = kwargs.get('page', 1)
    page_size = kwargs.get('page_size', 50)
    sort_by = kwargs.get('sort_by', 'created_at_desc')
    filters = {k: v for k, v in kwargs.items() if k not in ['db', 'page', 'page_size', 'sort_by'] and v and v != 'all'}

    orders_view = get_orders_view()
    shipments_view = get_shipments_view()

    # Subinterogare pentru a agrega expedierile (shipments) per comandă într-un array JSON
    shipments_subq = (
        select(
            shipments_view.c.order_id,
            json_agg(
                func.jsonb_build_object(
                    'awb', shipments_view.c.awb,
                    'courier', shipments_view.c.courier,
                    'last_status', shipments_view.c.last_status,
                    'printed_at', shipments_view.c.printed_at,
                    'derived_status', shipments_view.c.shipment_derived_status
                )
            ).label('shipments_data')
        )
        .group_by(shipments_view.c.order_id)
        .subquery('shipments_agg')
    )

    # Construim interogarea principală
    base_query = select(
        orders_view,
        models.Store.name.label('store_name'),
        shipments_subq.c.shipments_data
    ).select_from(orders_view)

    # Join-uri
    base_query = base_query.join(models.Store, orders_view.c.store_id == models.Store.id)
    base_query = base_query.outerjoin(shipments_subq, orders_view.c.id == shipments_subq.c.order_id)
    
    # Adăugăm join-uri condiționale pentru filtrare
    if filters.get('sku'):
        base_query = base_query.join(models.LineItem, orders_view.c.id == models.LineItem.order_id)
    if filters.get('category') and filters['category'] != 'all' and filters['category'].isdigit():
        base_query = base_query.join(models.store_category_map, models.Store.id == models.store_category_map.c.store_id)
    
    # --- Aplicare Filtre ---
    conditions = []
    if store_domain := filters.get('store'):
        conditions.append(models.Store.domain == store_domain)
    if category_id := filters.get('category'):
        if category_id.isdigit():
            conditions.append(models.store_category_map.c.category_id == int(category_id))
    if sku := filters.get('sku'):
        conditions.append(models.LineItem.sku.ilike(f"%{sku}%"))

    # Filtre simple mapate pe coloanele din view
    simple_filters_map = {
        'address_status': orders_view.c.address_status,
        'financial_status': orders_view.c.financial_status,
        'derived_status': orders_view.c.derived_status,
        'fulfillment_status': orders_view.c.shopify_status,
    }
    for key, column in simple_filters_map.items():
        if value := filters.get(key):
            conditions.append(column == value)
    
    if search_query := filters.get('order_q'):
        search_terms = [t.strip() for t in search_query.replace(' ', ',').split(',') if t.strip()]
        if search_terms:
            awb_subquery = select(models.Shipment.order_id).where(models.Shipment.awb.in_(search_terms)).distinct()
            conditions.append(or_(
                orders_view.c.name.in_(search_terms),
                orders_view.c.customer.ilike(f"%{search_terms[0]}%"), # căutare parțială pentru client
                orders_view.c.id.in_(awb_subquery)
            ))

    if conditions:
        base_query = base_query.where(and_(*conditions))

    # Pas 1: Numărăm totalul de rezultate (o interogare separată pentru eficiență)
    count_query = select(func.count()).select_from(base_query.alias("count_alias"))
    total_count = await db.scalar(count_query)

    if not total_count:
        return [], 0

    # Pas 2: Aplicăm sortarea și paginarea
    sort_key, _, sort_dir = sort_by.rpartition('_')
    sort_direction = desc if sort_dir == 'desc' else asc
    
    sort_map = {
        'created_at': orders_view.c.created_at,
        'order_name': orders_view.c.name,
        'order_status': orders_view.c.derived_status,
    }
    # Notă: Sortarea după statusul AWB-ului sau data printării devine complexă.
    # Momentan, sortarea se va baza pe statusul agregat al comenzii.
    sort_column = sort_map.get(sort_key, orders_view.c.created_at)
    
    paginated_query = base_query.order_by(sort_direction(sort_column).nullslast()) \
                                .offset((page - 1) * page_size).limit(page_size)

    # Executăm interogarea finală
    results = await db.execute(paginated_query)
    paginated_orders = [dict(row._mapping) for row in results]

    return paginated_orders, total_count