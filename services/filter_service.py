from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload, aliased
from sqlalchemy.sql.selectable import Select
from sqlalchemy import select, and_, or_, func, desc, asc, case, literal_column, table, column
import models
from settings import settings

# --- Start Helper Functions ---

def get_orders_view():
    """Creează și returnează un obiect Table pentru vizualizarea comenzilor."""
    return table(
        "orders_with_derived_status",
        column("id"), column("store_id"), column("name"), column("customer"),
        column("created_at"), column("fulfilled_at"), column("address_status"),
        column("financial_status"), column("shopify_status"), column("derived_status")
    )

def get_shipments_view():
    """Creează și returnează un obiect Table pentru vizualizarea livrărilor."""
    return table(
        "shipments_with_derived_status",
        column("id"), column("order_id"), column("courier"), column("awb"),
        column("printed_at"), column("last_status")
    )

# --- End Helper Functions ---


def _apply_filters_to_query(base_query: Select, filters: Dict[str, Any], orders_view, shipments_view) -> Select:
    """Aplică condițiile de join și filtrare pe o interogare existentă."""
    query = base_query.outerjoin(shipments_view, orders_view.c.id == shipments_view.c.order_id)

    conditions = []
    
    # Adaugă join-uri și condiții de bază
    if filters.get('store') and filters['store'] != 'all':
        query = query.join(models.Store, orders_view.c.store_id == models.Store.id)
        conditions.append(models.Store.domain == filters['store'])

    if filters.get('category') and filters['category'] != 'all' and filters['category'].isdigit():
        # Asigură-te că join-ul cu 'stores' există deja dacă e necesar
        if not any(isinstance(from_obj, type(models.Store.__table__)) for from_obj in query.froms):
             query = query.join(models.Store, orders_view.c.store_id == models.Store.id)
        query = query.join(models.store_category_map, models.Store.id == models.store_category_map.c.store_id)
        conditions.append(models.store_category_map.c.category_id == int(filters['category']))
        
    if filters.get('sku'):
        query = query.join(models.LineItem, orders_view.c.id == models.LineItem.order_id)
        conditions.append(models.LineItem.sku.ilike(f"%{filters['sku']}%"))

    # Condiții de filtrare simple
    simple_filters = {
        'address_status': orders_view.c.address_status,
        'financial_status': orders_view.c.financial_status,
        'shopify_status': orders_view.c.shopify_status,
        'derived_status': orders_view.c.derived_status,
        'courier': shipments_view.c.courier
    }
    for key, col in simple_filters.items():
        if (value := filters.get(key)) and value != 'all':
            conditions.append(col == value)

    if filters.get('order_q'):
        search_terms = [t.strip() for t in filters['order_q'].replace(' ', ',').split(',') if t.strip()]
        if search_terms:
            subquery = select(shipments_view.c.order_id).where(shipments_view.c.awb.in_(search_terms)).distinct()
            conditions.append(or_(
                orders_view.c.name.in_(search_terms),
                orders_view.c.customer.in_(search_terms),
                orders_view.c.id.in_(subquery)
            ))

    if filters.get('date_from') or filters.get('date_to'):
        date_column_map = {'created_at': orders_view.c.created_at, 'fulfilled_at': orders_view.c.fulfilled_at, 'printed_at': shipments_view.c.printed_at}
        if date_column := date_column_map.get(filters.get('date_filter_type')):
            try:
                if date_from := filters.get('date_from'):
                    conditions.append(date_column >= datetime.fromisoformat(date_from))
                if date_to := filters.get('date_to'):
                    conditions.append(date_column < (datetime.fromisoformat(date_to) + timedelta(days=1)))
            except ValueError: pass

    if (cs_status := filters.get('courier_status_group')) and cs_status != 'all':
        if cs_status == 'fara_awb': conditions.append(shipments_view.c.awb.is_(None))
        elif statuses := settings.COURIER_STATUS_MAP.get(cs_status, (None, []))[1]:
            conditions.append(shipments_view.c.last_status.in_(statuses))

    if (p_status := filters.get('printed_status')) and p_status != 'all':
        if p_status == 'printed': conditions.append(shipments_view.c.printed_at.isnot(None))
        elif p_status == 'neprintat': conditions.append(and_(shipments_view.c.awb.isnot(None), shipments_view.c.printed_at.is_(None)))
        elif p_status == 'fara_awb': conditions.append(shipments_view.c.awb.is_(None))

    if conditions:
        query = query.where(and_(*conditions))

    return query


async def apply_filters(db: AsyncSession, **kwargs) -> Tuple[List[models.Order], int]:
    """Preia și paginează comenzile, folosind VIEW-uri în mod consistent."""
    page, page_size, sort_by = kwargs.get('page', 1), kwargs.get('page_size', 50), kwargs.get('sort_by', 'created_at_desc')
    active_filters = {k: v for k, v in kwargs.items() if k not in ['db', 'page', 'page_size', 'sort_by'] and v and v != 'all'}
    active_filters['sort_by'] = sort_by

    orders_view = get_orders_view()
    shipments_view = get_shipments_view()

    # Pas 1: Numără totalul de rezultate filtrate
    count_q = select(func.count(orders_view.c.id.distinct())).select_from(orders_view)
    count_q = _apply_filters_to_query(count_q, active_filters, orders_view, shipments_view)
    total_count = await db.scalar(count_q)

    if total_count == 0:
        return [], 0

    # Pas 2: Obține ID-urile pentru pagina curentă
    ids_q = select(orders_view.c.id).select_from(orders_view)
    ids_q = _apply_filters_to_query(ids_q, active_filters, orders_view, shipments_view)
    
    sort_key, _, sort_dir = sort_by.rpartition('_')
    sort_direction = desc if sort_dir == 'desc' else asc
    
    sort_map = {
        'created_at': orders_view.c.created_at, 'order_name': orders_view.c.name,
        'order_status': orders_view.c.derived_status, 'awb_status': shipments_view.c.last_status,
        'printed_at': shipments_view.c.printed_at, 'awb': shipments_view.c.awb
    }
    sort_column = sort_map.get(sort_key, orders_view.c.created_at)

    ids_q = ids_q.group_by(orders_view.c.id, sort_column).order_by(sort_direction(sort_column).nullslast()) \
                 .offset((page - 1) * page_size).limit(page_size)

    paginated_order_ids = (await db.execute(ids_q)).scalars().all()

    if not paginated_order_ids:
        return [], total_count

    # Pas 3: Încarcă obiectele ORM complete pentru ID-urile obținute
    results_q = select(models.Order).where(models.Order.id.in_(paginated_order_ids)).options(
        selectinload(models.Order.shipments),
        selectinload(models.Order.line_items),
        joinedload(models.Order.store)
    )

    # Re-ordonează rezultatele în aceeași ordine ca ID-urile paginate
    all_results = (await db.execute(results_q)).unique().scalars().all()
    result_map = {order.id: order for order in all_results}
    ordered_results = [result_map[id] for id in paginated_order_ids if id in result_map]

    return ordered_results, total_count


async def get_filter_counts(db: AsyncSession, active_filters: Dict[str, Any]) -> Dict[str, Any]:
    """Calculează numărul de comenzi pentru fiecare grup de filtre."""
    counts = {}
    filter_groups = {
        'address_status': 'address_status', 'financial_status': 'financial_status',
        'derived_status': 'derived_status', 'courier': 'courier',
        'printed_status': 'printed_status', 'courier_status_group': 'courier_status_group'
    }

    orders_view = get_orders_view()
    shipments_view = get_shipments_view()

    for group_key, col_name in filter_groups.items():
        temp_filters = {k: v for k, v in active_filters.items() if k != group_key}
        
        subq = select(orders_view.c.id).select_from(orders_view)
        subq = _apply_filters_to_query(subq, temp_filters, orders_view, shipments_view).subquery()

        all_count_res = await db.execute(select(func.count()).select_from(subq))
        group_counts = {'all': all_count_res.scalar_one() or 0}

        count_q = None
        if group_key == 'courier':
            count_q = select(shipments_view.c.courier, func.count(shipments_view.c.order_id.distinct())) \
                .select_from(shipments_view).where(shipments_view.c.order_id.in_(select(subq.c.id))) \
                .group_by(shipments_view.c.courier)
        elif group_key in ['address_status', 'financial_status', 'derived_status']:
            count_q = select(orders_view.c[col_name], func.count()) \
                .select_from(orders_view).where(orders_view.c.id.in_(select(subq.c.id))) \
                .group_by(orders_view.c[col_name])
        
        if count_q is not None:
            results = await db.execute(count_q)
            for key, count in results.all():
                if key is not None: group_counts[str(key)] = count
        
        counts[group_key] = group_counts

    # Logica pentru 'printed_status' și 'courier_status_group' rămâne separată
    # ...

    stores_res = await db.execute(select(models.Store.id, models.Store.name).where(models.Store.is_active == True))
    stores = [{"id": r[0], "name": r[1]} for r in stores_res.all()]
    
    return {"statuses": counts.get('derived_status', {}), "stores": stores, "counts": counts}