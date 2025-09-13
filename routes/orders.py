from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from database import get_db
from models import Store
from services.filter_service import apply_filters

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    db: AsyncSession = Depends(get_db),
    store_id: Optional[int] = Query(None),
    awb_status: Optional[str] = Query(None),
    fulfillment_status: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query('order_date'),
    sort_dir: Optional[str] = Query('desc')
):
    current_filters = {
        "store_id": store_id,
        "awb_status": awb_status,
        "fulfillment_status": fulfillment_status,
        "payment_status": payment_status,
        "search": search,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }

    # --- LINIA CORECTATĂ ---
    # Am scos 'db' din apel, deoarece funcția asincronă nu mai are nevoie de el aici.
    orders_query = apply_filters(current_filters)
    
    # Executăm interogarea și preluăm rezultatele
    result = await db.execute(orders_query)
    # Folosim .unique() pentru a evita duplicatele cauzate de JOIN-uri
    orders = result.scalars().unique().all()
    
    # Preluăm magazinele pentru filtrul dropdown
    stores_result = await db.execute(select(Store))
    stores = stores_result.scalars().all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "orders": orders,
        "stores": stores,
        "awb_statuses": ["new", "pending", "generated", "error"],
        "fulfillment_statuses": ["fulfilled", "unfulfilled", "partially-fulfilled"],
        "payment_statuses": ["paid", "unpaid"],
        "current_filters": current_filters
    })