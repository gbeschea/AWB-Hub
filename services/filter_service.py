# services/filter_service.py

from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select
from sqlalchemy import select, and_, or_, func, desc, asc, table, column
import models
from settings import settings

# --- Helper Functions ---

def get_orders_view():
    return table("orders_with_derived_status", column("id"), column("store_id"), column("name"), column("customer"), column("created_at"), column("fulfilled_at"), column("address_status"), column("financial_status"), column("shopify_status"), column("derived_status"), column("total_price"), column("tags"), column("shipping_city"), column("shipping_country"))

def get_shipments_view():
    return table("shipments_with_derived_status", column("id"), column("order_id"), column("courier"), column("awb"), column("printed_at"), column("last_status"), column("derived_status"))

def _apply_filters_to_query(base_query: Select, filters: Dict[str, Any], orders_view, shipments_view) -> Select:
    # Această funcție aplică filtrele pe o interogare existentă
    query = base_query.outerjoin(shipments_view, orders_view.c.id == shipments_view.c.order_id)
    query = query.join(models.Store, orders_view.c.store_id == models.Store.id)

    if filters.get('sku'):
        query = query.join(models.LineItem, orders_view.c.id == models.LineItem.order_id)
    if filters.get('category') and filters['category'] != 'all' and filters['category'].isdigit():
        query = query.join(models.store_category_map, models.Store.id == models.store_category_map.c.store_id)

    conditions = []
    if store_domain := filters.get('store'):
        if store_domain != 'all':
            conditions.append(models.Store.domain == store_domain)
    if category_id := filters.get('category'):
        if category_id.isdigit():
            conditions.append(models.store_category_map.c.category_id == int(category_id))
    if sku := filters.get('sku'):
        conditions.append(models.LineItem.sku.ilike(f"%{sku}%"))

    simple_filters_map = {'address_status': orders_view.c.address_status, 'financial_status': orders_view.c.financial_status, 'derived_status': orders_view.c.derived_status, 'fulfillment_status': orders_view.c.shopify_status, 'courier': shipments_view.c.courier}
    for key, col in simple_filters_map.items():
        if (value := filters.get(key)) and value != 'all':
            conditions.append(col == value)

    if (search_query := filters.get('order_q')):
        search_terms = [t.strip() for t in search_query.replace(' ', ',').split(',') if t.strip()]
        if search_terms:
            awb_subquery = select(models.Shipment.order_id).where(models.Shipment.awb.in_(search_terms)).distinct()
            conditions.append(or_(orders_view.c.name.in_(search_terms), orders_view.c.customer.ilike(f"%{search_terms[0]}%"), orders_view.c.id.in_(awb_subquery)))

    if conditions:
        query = query.where(and_(*conditions))
    return query

async def apply_filters_and_get_orders(db: AsyncSession, **kwargs) -> Tuple[List[Dict[str, Any]], int]:
    page = kwargs.get('page', 1)
    page_size = kwargs.get('page_size', 50)
    sort_by = kwargs.get('sort_by', 'created_at_desc')
    filters = {k: v for k, v in kwargs.items() if k not in ['db', 'page', 'page_size', 'sort_by'] and v}

    orders_view = get_orders_view()
    shipments_view = get_shipments_view()

    id_query_base = select(orders_view.c.id).select_from(orders_view)
    id_query_filtered = _apply_filters_to_query(id_query_base, filters, orders_view, shipments_view)
    
    count_query = select(func.count(id_query_filtered.distinct().alias('distinct_ids').c.id))
    total_count = await db.scalar(count_query)

    if not total_count:
        return [], 0

    sort_key, _, sort_dir = sort_by.rpartition('_')
    sort_direction = desc if sort_dir == 'desc' else asc
    sort_map = {'created_at': orders_view.c.created_at, 'order_name': orders_view.c.name, 'order_status': orders_view.c.derived_status}
    sort_column = sort_map.get(sort_key, orders_view.c.created_at)

    paginated_ids_query = id_query_filtered.group_by(orders_view.c.id, sort_column).order_by(sort_direction(sort_column).nullslast()).offset((page - 1) * page_size).limit(page_size)
    paginated_ids_result = await db.execute(paginated_ids_query)
    paginated_ids = [row.id for row in paginated_ids_result]

    if not paginated_ids:
        return [], total_count

    orders_query = select(orders_view, models.Store.name.label('store_name')).join(models.Store, orders_view.c.store_id == models.Store.id).where(orders_view.c.id.in_(paginated_ids))
    orders_result = await db.execute(orders_query)
    orders_map = {row.id: dict(row._mapping) for row in orders_result}

    shipments_query = select(shipments_view).where(shipments_view.c.order_id.in_(paginated_ids)).order_by(shipments_view.c.id)
    shipments_result = await db.execute(shipments_query)
    for shipment in shipments_result:
        order_id = shipment.order_id
        if order_id in orders_map:
            if 'shipments_data' not in orders_map[order_id]:
                orders_map[order_id]['shipments_data'] = []
            orders_map[order_id]['shipments_data'].append(dict(shipment._mapping))
    
    ordered_results = [orders_map[id] for id in paginated_ids if id in orders_map]
    return ordered_results, total_count

async def get_filter_counts(db: AsyncSession, active_filters: Dict[str, Any]) -> Dict[str, Any]:
    counts = {}
    
    # --- AICI ERA EROAREA: Variabilele trebuiau definite în interiorul funcției ---
    orders_view = get_orders_view()
    shipments_view = get_shipments_view()
    
    filter_groups = {'derived_status': orders_view.c.derived_status, 'courier': shipments_view.c.courier}
    
    # Obținem ID-urile comenzilor care corespund filtrelor active (fără a considera grupul curent)
    base_id_query = select(orders_view.c.id).select_from(orders_view)
    
    for group_key, column in filter_groups.items():
        # Excludem filtrul curent din setul de filtre active pentru a număra corect opțiunile
        temp_filters = {k: v for k, v in active_filters.items() if k != group_key and v != 'all'}
        
        filtered_ids_subquery = _apply_filters_to_query(base_id_query, temp_filters, orders_view, shipments_view).distinct().alias(f'filtered_ids_{group_key}').c.id

        if group_key == 'courier':
            count_query = select(column, func.count(shipments_view.c.order_id.distinct())) \
                .where(shipments_view.c.order_id.in_(select(filtered_ids_subquery))) \
                .group_by(column)
        else: # 'derived_status'
            count_query = select(column, func.count(orders_view.c.id.distinct())) \
                .where(orders_view.c.id.in_(select(filtered_ids_subquery))) \
                .group_by(column)
        
        results = await db.execute(count_query)
        counts[group_key] = {str(key): count for key, count in results if key is not None}

    stores_res = await db.execute(select(models.Store.id, models.Store.name, models.Store.domain).where(models.Store.is_active == True))
    stores = [{"id": r.id, "name": r.name, "domain": r.domain} for r in stores_res]
    
    return {"statuses": counts.get('derived_status', {}), "couriers": counts.get('courier', {}), "stores": stores}