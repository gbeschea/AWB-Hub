from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload, aliased
from sqlalchemy.sql.selectable import Select
from sqlalchemy import select, text, and_, or_, func, desc, asc, case, literal_column
import models
from settings import settings

def _get_query_components(filters: Dict[str, Any], orders_alias, shipments_alias) -> list:
    """Construiește o listă de condiții de filtrare SQLAlchemy, folosind alias-uri pentru VIEW-uri."""
    conditions = []

    if filters.get('store') and filters['store'] != 'all':
        conditions.append(models.Store.domain == filters['store'])

    if filters.get('category') and filters['category'] != 'all' and filters['category'].isdigit():
        conditions.append(models.store_category_map.c.category_id == int(filters['category']))

    if filters.get('courier') and filters['courier'] != 'all':
        conditions.append(shipments_alias.courier == filters['courier'])

    if filters.get('address_status') and filters['address_status'] != 'all':
        conditions.append(orders_alias.address_status == filters['address_status'])

    if filters.get('financial_status') and filters['financial_status'] != 'all':
        conditions.append(orders_alias.financial_status == filters['financial_status'])

    if filters.get('fulfillment_status') and filters['fulfillment_status'] != 'all':
        conditions.append(orders_alias.shopify_status == filters['fulfillment_status'])

    if filters.get('derived_status') and filters['derived_status'] != 'all':
        conditions.append(orders_alias.derived_status == filters['derived_status'])

    if filters.get('order_q'):
        search_terms = [t.strip() for t in filters['order_q'].replace(' ', ',').split(',') if t.strip()]
        if search_terms:
            subquery = select(models.Shipment.order_id).where(models.Shipment.awb.in_(search_terms)).distinct()
            conditions.append(or_(
                orders_alias.name.in_(search_terms),
                orders_alias.customer.in_(search_terms),
                orders_alias.id.in_(subquery)
            ))

    if filters.get('sku'):
        conditions.append(models.LineItem.sku.ilike(f"%{filters['sku']}%"))

    if filters.get('date_from') or filters.get('date_to'):
        date_column_map = {'created_at': orders_alias.created_at, 'fulfilled_at': orders_alias.fulfilled_at, 'printed_at': shipments_alias.printed_at}
        if date_column := date_column_map.get(filters.get('date_filter_type')):
            try:
                if filters.get('date_from'): conditions.append(date_column >= datetime.fromisoformat(filters['date_from']))
                if filters.get('date_to'): conditions.append(date_column < (datetime.fromisoformat(filters['date_to']) + timedelta(days=1)))
            except ValueError: pass

    if (cs_status := filters.get('courier_status_group')) and cs_status != 'all':
        if cs_status == 'fara_awb': conditions.append(shipments_alias.awb.is_(None))
        elif statuses := settings.COURIER_STATUS_MAP.get(cs_status, (None, []))[1]:
            conditions.append(shipments_alias.last_status.in_(statuses))

    if (p_status := filters.get('printed_status')) and p_status != 'all':
        if p_status == 'printed': conditions.append(shipments_alias.printed_at.isnot(None))
        elif p_status == 'neprintat': conditions.append(and_(shipments_alias.awb.isnot(None), shipments_alias.printed_at.is_(None)))
        elif p_status == 'fara_awb': conditions.append(shipments_alias.awb.is_(None))

    return conditions

def _apply_joins_and_filters(base_query: Select, filters: Dict[str, Any], orders_alias, shipments_alias) -> Select:
    """Aplică join-urile și filtrele necesare pe o interogare care folosește VIEW-uri."""
    query = base_query
    
    query = query.outerjoin(shipments_alias, orders_alias.id == shipments_alias.order_id)
    
    if filters.get('sku'):
        query = query.join(models.LineItem, orders_alias.id == models.LineItem.order_id)
    if filters.get('store') or filters.get('category'):
        query = query.join(models.Store, orders_alias.store_id == models.Store.id)
    if filters.get('category'):
        query = query.join(models.store_category_map, models.Store.id == models.store_category_map.c.store_id)

    conditions = _get_query_components(filters, orders_alias, shipments_alias)
    if conditions:
        query = query.where(and_(*conditions))

    return query

async def apply_filters(db: AsyncSession, **kwargs) -> Tuple[List[models.Order], int]:
    """Preia și paginează comenzile, adaptat complet pentru arhitectura cu VIEW-uri."""
    page, page_size, sort_by = kwargs.get('page', 1), kwargs.get('page_size', 50), kwargs.get('sort_by', 'created_at_desc')
    active_filters = {k: v for k, v in kwargs.items() if k not in ['db', 'page', 'page_size', 'sort_by'] and v and v != 'all'}

    orders_view = aliased(models.Order, name="orders_with_derived_status")
    shipments_view = aliased(models.Shipment, name="shipments_with_derived_status")

    # Interogare pentru a număra totalul
    count_q_base = select(func.count(orders_view.id.distinct())).select_from(orders_view)
    count_q = _apply_joins_and_filters(count_q_base, active_filters, orders_view, shipments_view)
    total_count_res = await db.execute(count_q)
    total_count = total_count_res.scalar_one()

    if total_count == 0:
        return [], 0

    # Interogare pentru a prelua ID-urile paginante
    ids_q_base = select(orders_view.id).select_from(orders_view)
    ids_q = _apply_joins_and_filters(ids_q_base, active_filters, orders_view, shipments_view)
    ids_q = ids_q.group_by(orders_view.id)

    # Logica de sortare complexă, adaptată pentru alias-uri
    sort_key, _, sort_dir = sort_by.rpartition('_')
    sort_direction = desc if sort_dir == 'desc' else asc
    
    if sort_key == 'line_items_group':
        ids_q = ids_q.outerjoin(models.LineItem)
        product_signature = literal_column("string_agg(line_items.quantity::TEXT || 'x' || line_items.sku, ';' ORDER BY line_items.sku)")
        unique_sku_count = func.count(models.LineItem.sku.distinct())
        single_sku_quantity = case((unique_sku_count == 1, func.sum(models.LineItem.quantity)), else_=999)
        first_sku = func.min(models.LineItem.sku)
        final_sort = [sort_direction(unique_sku_count), sort_direction(first_sku), sort_direction(single_sku_quantity), sort_direction(product_signature)]
        ids_q = ids_q.group_by(orders_view.id)
    else:
        sort_map = {'created_at': orders_view.created_at, 'order_name': orders_view.name, 'order_status': orders_view.derived_status, 'awb_status': shipments_view.last_status, 'printed_at': shipments_view.printed_at, 'awb': shipments_view.awb}
        if sort_key in sort_map:
            ids_q = ids_q.group_by(sort_map[sort_key])
            final_sort = [sort_direction(sort_map[sort_key]).nullslast()]
        else: 
            ids_q = ids_q.group_by(orders_view.created_at)
            final_sort = [desc(orders_view.created_at)]

    ids_q = ids_q.order_by(*final_sort).offset((page - 1) * page_size).limit(page_size)
    paginated_order_ids_res = await db.execute(ids_q)
    paginated_order_ids = paginated_order_ids_res.scalars().all()

    if not paginated_order_ids:
        return [], total_count

    # Interogarea finală pentru a prelua obiectele complete
    results_q = select(orders_view).options(
        selectinload(orders_view.shipments.of_type(shipments_view)),
        selectinload(orders_view.line_items),
        joinedload(orders_view.store)
    ).where(orders_view.id.in_(paginated_order_ids))
    
    results_q = results_q.order_by(*final_sort)

    all_results_res = await db.execute(results_q)
    all_results = all_results_res.unique().scalars().all()
    
    result_map = {order.id: order for order in all_results}
    ordered_results = [result_map[id] for id in paginated_order_ids if id in result_map]

    return ordered_results, total_count


async def get_filter_counts(db: AsyncSession, active_filters: Dict[str, Any]) -> Dict[str, Any]:
    """Calculează numărul de comenzi pentru fiecare grup de filtre, adaptat pentru VIEW-uri."""
    counts = {}
    filter_groups = {
        'store': models.Store.domain, 'category': models.store_category_map.c.category_id,
        'courier': 'courier', 'address_status': 'address_status', 'financial_status': 'financial_status',
        'fulfillment_status': 'shopify_status', 'printed_status': 'printed_status',
        'courier_status_group': 'courier_status_group', 'derived_status': 'derived_status'
    }

    orders_view_alias = aliased(models.Order, name="orders_with_derived_status")
    shipments_view_alias = aliased(models.Shipment, name="shipments_with_derived_status")

    for group_key, col in filter_groups.items():
        temp_filters = {k: v for k, v in active_filters.items() if k != group_key}
        
        base_subquery = select(orders_view_alias.id.distinct()).select_from(orders_view_alias)
        subq = _apply_joins_and_filters(base_subquery, temp_filters, orders_view_alias, shipments_view_alias).subquery()

        all_count_res = await db.execute(select(func.count()).select_from(subq))
        group_counts = {'all': all_count_res.scalar_one()}

        if group_key == 'courier_status_group':
            for status_group, (_, statuses) in settings.COURIER_STATUS_MAP.items():
                if statuses: 
                    res = await db.execute(select(func.count(models.Order.id.distinct())).join(models.Shipment).where(models.Order.id.in_(select(subq)), models.Shipment.last_status.in_(statuses)))
                    group_counts[status_group] = res.scalar_one()
            res_fara_awb = await db.execute(select(func.count(models.Order.id.distinct())).outerjoin(models.Shipment).where(models.Order.id.in_(select(subq)), models.Shipment.awb.is_(None)))
            group_counts['fara_awb'] = res_fara_awb.scalar_one()
        
        elif group_key == 'printed_status':
            res_p = await db.execute(select(func.count(models.Order.id.distinct())).join(models.Shipment).where(models.Order.id.in_(select(subq)), models.Shipment.printed_at.isnot(None)))
            group_counts['printed'] = res_p.scalar_one()
            res_n = await db.execute(select(func.count(models.Order.id.distinct())).join(models.Shipment).where(models.Order.id.in_(select(subq)), and_(models.Shipment.awb.isnot(None), models.Shipment.printed_at.is_(None))))
            group_counts['neprintat'] = res_n.scalar_one()
            res_f = await db.execute(select(func.count(models.Order.id.distinct())).outerjoin(models.Shipment).where(models.Order.id.in_(select(subq)), models.Shipment.awb.is_(None)))
            group_counts['fara_awb'] = res_f.scalar_one()

        else:
            count_q = None
            base_count_query = select(func.count(models.Order.id.distinct()))
            
            if group_key == 'courier':
                count_q = select(shipments_view_alias.courier, func.count(shipments_view_alias.order_id.distinct())).select_from(shipments_view_alias).where(shipments_view_alias.order_id.in_(select(subq))).group_by(shipments_view_alias.courier)
            elif group_key in ['store', 'category']:
                # Această numărătoare necesită join-uri complexe și e mai bine să o lași pe 'all'
                pass
            else: # Rulează pe orders_view
                count_q = select(getattr(orders_view_alias, col), func.count()).select_from(orders_view_alias).where(orders_view_alias.id.in_(select(subq))).group_by(getattr(orders_view_alias, col))
            
            if count_q is not None:
                results = await db.execute(count_q)
                for key, count in results.all():
                    if key is not None: group_counts[str(key)] = count
        
        counts[group_key] = group_counts

    stores_res = await db.execute(select(models.Store.id, models.Store.name).where(models.Store.is_active == True))
    stores = [{"id": r[0], "name": r[1]} for r in stores_res.all()]
    
    return {"statuses": counts.get('derived_status', {}), "stores": stores, "counts": counts}