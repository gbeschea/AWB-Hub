import io, csv, math, json, re
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_
import models
from database import get_db
from services import filter_service
from settings import settings
from dependencies import get_templates, get_pagination_numbers
from async_lru import alru_cache

router = APIRouter(tags=['Orders & View'])

@alru_cache(maxsize=128, ttl=300)
async def get_filter_dropdown_data(db: AsyncSession) -> dict:
    stores_res = await db.execute(select(models.Store).order_by(models.Store.name))
    categories_res = await db.execute(select(models.StoreCategory).order_by(models.StoreCategory.name))
    couriers_list_res = await db.execute(select(models.Shipment.courier).distinct())
    
    return {
        "stores": stores_res.scalars().all(),
        "categories": categories_res.scalars().all(),
        "couriers_list": sorted([c[0] for c in couriers_list_res.all() if c[0]]),
    }

@router.get('/view', response_class=HTMLResponse, name='view_orders')
async def view(
    request: Request, db: AsyncSession = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates),
    page: int = Query(1, ge=1), page_size: int = Query(50), store: str = Query('all'),
    category: str = Query('all'), courier: str = Query('all'),
    financial_status: Optional[str] = Query('all'), fulfillment_status: Optional[str] = Query('all'),
    courier_status_group: str = Query('all'), derived_status: str = Query('all'),
    address_status: str = Query('all'),
    sku: Optional[str] = Query(None), date_filter_type: str = Query('created_at'),
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    order_q: Optional[str] = Query(None), printed_status: str = Query('all'),
    days: int = Query(30), sort_by: str = Query('created_at_desc')
):
    active_filters = {k: v for k, v in request.query_params.items() if v and v not in ['all', ''] and k not in ['page', 'page_size', 'sort_by']}
    
    filter_counts = await filter_service.get_filter_counts(db, active_filters)
    paginated_orders, total_orders = await filter_service.apply_filters(db=db, **active_filters, page=page, page_size=page_size, sort_by=sort_by)
    filter_dropdown_data = await get_filter_dropdown_data(db)
    
    cat_id_to_template_res = await db.execute(select(models.CourierCategory.id, models.CourierCategory.tracking_url_template).where(models.CourierCategory.tracking_url_template.isnot(None)))
    courier_to_cat_id_res = await db.execute(select(models.courier_category_map.c.courier_key, models.courier_category_map.c.category_id))
    cat_id_to_template_map = dict(cat_id_to_template_res.all())
    courier_to_cat_id_map = dict(courier_to_cat_id_res.all())
    courier_tracking_map = {c: cat_id_to_template_map.get(cat_id) for c, cat_id in courier_to_cat_id_map.items() if cat_id in cat_id_to_template_map}

    def normalize_status(text: str) -> str:
        if not text: return ""
        text = text.lower().strip()
        replacements = {'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ț': 't'}
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        return text

    RAW_STATUS_TO_FRIENDLY_NAME = {
        normalize_status(s): name
        for group, (name, statuses) in settings.COURIER_STATUS_MAP.items()
        for s in statuses
    }

    def get_shipment_sort_key(shipment):
        return (shipment.fulfillment_created_at or datetime.min.replace(tzinfo=timezone.utc), shipment.id)

    for order in paginated_orders:
        order.latest_shipment = max(order.shipments, key=get_shipment_sort_key) if order.shipments else None
        order.line_items_str = ", ".join([f"{li.quantity}x {li.sku or li.title}" for li in order.line_items])
        raw_status = (order.latest_shipment.last_status or '').strip() if order.latest_shipment else ''
        normalized_raw_status = normalize_status(raw_status)
        order.mapped_courier_status = RAW_STATUS_TO_FRIENDLY_NAME.get(normalized_raw_status, raw_status)

    total_pages = math.ceil(total_orders / page_size) if total_orders > 0 else 1
    page_numbers = get_pagination_numbers(page, total_pages)

    derived_status_options = [ "🚦 On Hold", "📦 Neprocesată", "✈️ Procesată", "⏰ Netrimisă (Alertă)", "🚚 Expediată", "🚚 În curs de livrare", "✅ Livrată", "❌ Refuzată", "❌ Anulată" ]
    financial_status_options = ["pending", "paid", "partially_paid", "refunded", "partially_refunded", "voided"]
    fulfillment_status_options = ["fulfilled", "unfulfilled", "partially_fulfilled", "restocked", "cancelled"]
    courier_status_group_options = [(key, val[0]) for key, val in settings.COURIER_STATUS_MAP.items()]
    address_status_options = ["valid", "invalid", "nevalidat"]

    context = {
        "request": request, "orders": paginated_orders,
        "stores": filter_dropdown_data["stores"],
        "categories": filter_dropdown_data["categories"],
        "couriers": filter_dropdown_data["couriers_list"],
        "derived_status_options": derived_status_options,
        "financial_status_options": financial_status_options,
        "fulfillment_status_options": fulfillment_status_options,
        "courier_status_group_options": courier_status_group_options,
        "address_status_options": address_status_options,
        "active_filters": active_filters,
        "page": page, "page_size": page_size,
        "total_orders": total_orders,
        "total_pages": total_pages,
        "page_numbers": page_numbers,
        "courier_tracking_map": courier_tracking_map,
        "filter_counts": filter_counts,
    }
    return templates.TemplateResponse("index.html", context)