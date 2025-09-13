# routes/orders.py

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.templating import Jinja2Templates

import models
from database import get_db
from services import filter_service

templates = Jinja2Templates(directory="templates")
router = APIRouter()

@router.get("/view", response_class=HTMLResponse, name="view_orders")
async def view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
    store: str = "all",
    category: str = "all",
    fulfillment_status: str = "all",
    financial_status: str = "all",
    derived_status: str = "all",
    address_status: str = "all",
    courier: str = "all",
    printed_status: str = "all",
    courier_status_group: str = "all",
    order_q: str = None,
    date_filter_type: str = "created_at",
    date_from: str = None,
    date_to: str = None,
    sort_by: str = "created_at_desc",
    sku: str = None,
):
    active_filters = {
        "page": page, "page_size": page_size, "store": store, "category": category,
        "fulfillment_status": fulfillment_status, "financial_status": financial_status,
        "derived_status": derived_status, "address_status": address_status,
        "courier": courier, "printed_status": printed_status,
        "courier_status_group": courier_status_group, "order_q": order_q,
        "date_filter_type": date_filter_type, "date_from": date_from,
        "date_to": date_to, "sort_by": sort_by, "sku": sku
    }

    def get_sort_url(sort_key_name: str):
        """Helper function to generate sorting URLs."""
        current_sort_key, _, current_sort_dir = sort_by.rpartition('_')
        if current_sort_key == sort_key_name and current_sort_dir == 'desc':
            next_sort_dir = 'asc'
        else:
            next_sort_dir = 'desc'
        
        new_sort_by = f"{sort_key_name}_{next_sort_dir}"
        
        # Rebuild query parameters safely
        new_params = request.query_params._dict.copy()
        new_params['sort_by'] = new_sort_by
        return request.url.replace(query=None).include_query_params(**new_params)

    filter_counts = await filter_service.get_filter_counts(db, active_filters)
    paginated_orders, total_orders = await filter_service.apply_filters_and_get_orders(db=db, **active_filters)
    
    total_pages = (total_orders + page_size - 1) // page_size
    store_categories = (await db.execute(select(models.StoreCategory))).scalars().all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "orders": paginated_orders,
            "total_orders": total_orders,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "active_filters": active_filters,
            "sort_by": sort_by,
            "filter_counts": filter_counts,
            "store_categories": store_categories,
            "get_sort_url": get_sort_url # Pass the helper function to the template
        },
    )