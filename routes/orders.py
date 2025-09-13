import models
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, asc, select
from sqlalchemy.orm import Session, selectinload
from database import get_db  # <--- THIS LINE IS THE FIX
from dependencies import get_flash_messages, get_stores_from_db, get_unfulfilled_orders_count, get_unprinted_orders_count
from typing import Optional

# ... (rest of the file remains the same)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SORTABLE_COLUMNS = {
    "order_number": models.Order.order_number,
    "order_date": models.Order.order_date,
    "status": models.Order.status,
    "customer_name": models.Order.customer_name,
    "awb": models.Order.awb,
}

@router.get("/", response_class=HTMLResponse)
async def get_orders(
    request: Request,
    db: Session = Depends(get_db),
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "desc",
    flash_messages: dict = Depends(get_flash_messages),
    stores=Depends(get_stores_from_db),
    unfulfilled_count=Depends(get_unfulfilled_orders_count),
    unprinted_count=Depends(get_unprinted_orders_count),
):
    """
    Handles displaying the main orders page with server-side sorting.
    """
    query = select(models.Order).options(selectinload(models.Order.shipments))

    # Apply sorting
    if sort_by in SORTABLE_COLUMNS:
        column = SORTABLE_COLUMNS[sort_by]
        if sort_order == "asc":
            query = query.order_by(asc(column))
        else:
            query = query.order_by(desc(column))
    else:
        query = query.order_by(models.Order.order_date.desc())

    result = await db.execute(query)
    orders = result.scalars().all()

    # Get unique statuses for the filter dropdown
    status_query = select(models.Order.status).distinct()
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
            "flash_messages": flash_messages,
            "unfulfilled_count": unfulfilled_count,
            "unprinted_count": unprinted_count,
            "current_sort_by": sort_by,
            "current_sort_order": sort_order,
        },
    )

# ... (rest of the file)