# gbeschea/awb-hub/AWB-Hub-28035206bac3a3437048d87acde55b68d0fb6085/routes/orders.py
import models
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, asc, select
from sqlalchemy.orm import Session, selectinload
from database import get_db
# Verifică acest import:
from dependencies import get_stores_from_db, get_unfulfilled_orders_count, get_unprinted_orders_count
from typing import Optional
from collections import Counter

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Definirea coloanelor sortabile
SORTABLE_COLUMNS = {
    "order_name": models.Order.name,
    "created_at": models.Order.created_at,
    "shopify_status": models.Order.shopify_status,
    "customer": models.Order.customer,
    "assigned_courier": models.Order.assigned_courier,
}

@router.get("/", response_class=HTMLResponse)
async def get_orders(
    request: Request,
    db: Session = Depends(get_db),
    sort_by: Optional[str] = "created_at", # Sortează implicit după dată
    sort_order: Optional[str] = "desc",
    stores=Depends(get_stores_from_db),
    unfulfilled_count=Depends(get_unfulfilled_orders_count),
    unprinted_count=Depends(get_unprinted_orders_count),
):
    """
    Afișează pagina principală a comenzilor cu sortare.
    """
    query = select(models.Order).options(
        selectinload(models.Order.shipments),
        selectinload(models.Order.store) # Asigură-te că încarci și magazinul
    )

    # Aplică sortarea
    if sort_by in SORTABLE_COLUMNS:
        column = SORTABLE_COLUMNS[sort_by]
        if sort_order == "asc":
            query = query.order_by(asc(column))
        else:
            query = query.order_by(desc(column))
    else:
        query = query.order_by(desc(models.Order.created_at))

    result = await db.execute(query)
    orders = result.scalars().unique().all()

    # Calculează numărul de comenzi pentru filtre
    store_counts = Counter(order.store.name for order in orders if order.store)
    filter_counts = {
        'store': {
            'all': len(orders),
            **dict(store_counts)
        }
    }

    # Obține statusurile unice pentru filtrul din dropdown
    status_query = select(models.Order.shopify_status).distinct()
    status_result = await db.execute(status_query)
    statuses = status_result.scalars().all()
    unique_statuses = sorted([status for status in statuses if status])

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "orders": orders,
            "stores": stores,
            "unique_statuses": unique_statuses,
            "unfulfilled_count": unfulfilled_count,
            "unprinted_count": unprinted_count,
            "current_sort_by": sort_by,
            "current_sort_order": sort_order,
            "filter_counts": filter_counts,
        },
    )