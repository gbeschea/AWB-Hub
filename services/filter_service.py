from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.sql.selectable import Select
from sqlalchemy import select, and_, or_, func, desc, asc, case, literal_column
import models
from settings import settings

def _get_query_components(filters: Dict[str, Any]) -> list:
    """Builds a list of SQLAlchemy filter conditions based on user input."""
    conditions = []

    if filters.get('store') and filters['store'] != 'all':
        conditions.append(models.Store.domain == filters['store'])

    if filters.get('category') and filters['category'] != 'all' and filters['category'].isdigit():
        conditions.append(models.store_category_map.c.category_id == int(filters['category']))

    if filters.get('courier') and filters['courier'] != 'all':
        conditions.append(models.Shipment.courier == filters['courier'])

    if filters.get('address_status') and filters['address_status'] != 'all':
        conditions.append(models.Order.address_status == filters['address_status'])

    if filters.get('financial_status') and filters['financial_status'] != 'all':
        conditions.append(models.Order.financial_status == filters['financial_status'])

    if filters.get('fulfillment_status') and filters['fulfillment_status'] != 'all':
        conditions.append(models.Order.shopify_status == filters['fulfillment_status'])

    if filters.get('derived_status') and filters['derived_status'] != 'all':
        conditions.append(models.Order.derived_status == filters['derived_status'])

    if filters.get('order_q'):
        search_terms = [t.strip() for t in filters['order_q'].replace(' ', ',').split(',') if t.strip()]
        if search_terms:
            conditions.append(or_(
                models.Order.name.in_(search_terms),
                models.Order.customer.in_(search_terms),
                models.Shipment.awb.in_(search_terms)
            ))

    if filters.get('sku'):
        conditions.append(models.LineItem.sku.ilike(f"%{filters['sku']}%"))

    if filters.get('date_from') or filters.get('date_to'):
        date_column_map = {'created_at': models.Order.created_at, 'fulfilled_at': models.Order.fulfilled_at, 'printed_at': models.Shipment.printed_at}
        if date_column := date_column_map.get(filters.get('date_filter_type')):
            try:
                if filters.get('date_from'): conditions.append(date_column >= datetime.fromisoformat(filters['date_from']))
                if filters.get('date_to'): conditions.append(date_column < (datetime.fromisoformat(filters['date_to']) + timedelta(days=1)))
            except ValueError: pass

    if (cs_status := filters.get('courier_status_group')) and cs_status != 'all':
        if cs_status == 'fara_awb': conditions.append(models.Shipment.awb.is_(None))
        elif statuses := settings.COURIER_STATUS_MAP.get(cs_status, (None, []))[1]:
            conditions.append(models.Shipment.last_status.in_(statuses))

    if (p_status := filters.get('printed_status')) and p_status != 'all':
        if p_status == 'printed': conditions.append(models.Shipment.printed_at.isnot(None))
        elif p_status == 'neprintat': conditions.append(models.Shipment.printed_at.is_(None))
        elif p_status == 'fara_awb': conditions.append(models.Shipment.awb.is_(None))

    return conditions

def _apply_joins_and_filters(base_query: Select, filters: Dict[str, Any]) -> Select:
    """Applies all necessary joins and conditions to a query."""
    query = base_query.outerjoin(models.Shipment, models.Order.id == models.Shipment.order_id)

    # Apply joins conditionally based on which filters are active
    if any(f in filters for f in ['sku']):
        query = query.join(models.LineItem, models.Order.id == models.LineItem.order_id)
    if any(f in filters for f in ['store', 'category']):
        query = query.join(models.Store, models.Order.store_id == models.Store.id)
    if any(f in filters for f in ['category']):
        query = query.join(models.store_category_map, models.Store.id == models.store_category_map.c.store_id)

    conditions = _get_query_components(filters)
    if conditions:
        query = query.where(and_(*conditions))

    return query

async def apply_filters(db: AsyncSession, **kwargs) -> Tuple[List[models.Order], int]:
    page, page_size, sort_by = kwargs.get('page', 1), kwargs.get('page_size', 50), kwargs.get('sort_by', 'created_at_desc')
    active_filters = {k: v for k, v in kwargs.items() if k not in ['db', 'page', 'page_size', 'sort_by'] and v and v != 'all'}

    count_q = _apply_joins_and_filters(select(func.count(models.Order.id.distinct())), active_filters)
    total_count_res = await db.execute(count_q)
    total_count = total_count_res.scalar_one()

    ids_q = _apply_joins_and_filters(select(models.Order.id), active_filters)

    sort_key, _, sort_dir = sort_by.rpartition('_')
    sort_direction = desc if sort_dir == 'desc' else asc
    ids_q = ids_q.group_by(models.Order.id)

    if sort_key == 'line_items_group':
        ids_q = ids_q.outerjoin(models.LineItem)
        product_signature = literal_column("string_agg(line_items.quantity::TEXT || 'x' || line_items.sku, ';' ORDER BY line_items.sku)")
        unique_sku_count = func.count(models.LineItem.sku.distinct())
        single_sku_quantity = case((unique_sku_count == 1, func.sum(models.LineItem.quantity)), else_=999)
        first_sku = func.min(models.LineItem.sku)
        final_sort = [sort_direction(unique_sku_count), sort_direction(first_sku), sort_direction(single_sku_quantity), sort_direction(product_signature)]
    else:
        sort_map = {'created_at': models.Order.created_at, 'order_name': models.Order.name, 'order_status': models.Order.derived_status, 'awb_status': models.Shipment.last_status, 'printed_at': models.Shipment.printed_at, 'awb': models.Shipment.awb}
        if sort_key in sort_map:
            if sort_key in ['awb_status', 'printed_at', 'awb']:
                ids_q = ids_q.group_by(models.Shipment.id)
            final_sort = [sort_direction(sort_map[sort_key]).nullslast()]
        else:
            final_sort = [desc(models.Order.created_at)]

    ids_q = ids_q.order_by(*final_sort).offset((page - 1) * page_size).limit(page_size)
    paginated_order_ids_res = await db.execute(ids_q)
    paginated_order_ids = paginated_order_ids_res.scalars().all()

    if not paginated_order_ids: return [], total_count

    results_q = select(models.Order).options(selectinload(models.Order.shipments), selectinload(models.Order.line_items), joinedload(models.Order.store)).where(models.Order.id.in_(paginated_order_ids))
    all_results_res = await db.execute(results_q)
    all_results = all_results_res.unique().scalars().all()
    result_map = {order.id: order for order in all_results}
    ordered_results = [result_map[id] for id in paginated_order_ids if id in result_map]

    return ordered_results, total_count


async def get_filter_counts(db: AsyncSession, active_filters: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    counts = {}
    filter_groups = {
        'store': models.Store.domain, 'category': models.store_category_map.c.category_id,
        'courier': models.Shipment.courier, 'address_status': models.Order.address_status,
        'financial_status': models.Order.financial_status, 'fulfillment_status': models.Order.shopify_status,
        'printed_status': 'printed_status', 'courier_status_group': 'courier_status_group',
        'derived_status': models.Order.derived_status
    }

    for group_key, col in filter_groups.items():
        temp_filters = {k: v for k, v in active_filters.items() if k != group_key}

        subq = _apply_joins_and_filters(select(models.Order.id.distinct()), temp_filters).subquery()

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
            # --- START MODIFICATION ---
            # Build the query for the specific group, explicitly starting from Orders
            count_q_base = select(col, func.count(models.Order.id.distinct())) \
                            .select_from(models.Order) \
                            .where(models.Order.id.in_(select(subq)))

            final_count_q = count_q_base
            # Apply joins needed *only for this specific group's column*
            if group_key == 'courier': final_count_q = final_count_q.join(models.Shipment)
            if group_key in ['store', 'category']: final_count_q = final_count_q.join(models.Store)
            if group_key == 'category': final_count_q = final_count_q.join(models.store_category_map)

            results = await db.execute(final_count_q.group_by(col))
            # --- END MODIFICATION ---

            for key, count in results.all():
                if key is not None: group_counts[str(key)] = count

        counts[group_key] = group_counts
    return counts
