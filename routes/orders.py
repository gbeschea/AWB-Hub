# Asigură-te că ai aceste importuri la începutul fișierului routes/orders.py
from typing import Optional
from collections import Counter
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, asc, desc
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

import models
from database import get_db, engine
from dependencies import get_stores_from_db, get_unfulfilled_orders_count, get_unprinted_orders_count
from dependencies import templates


# --- Aici începe router-ul și celelalte funcții ---
router = APIRouter()

# Presupun că ai aceste variabile definite undeva
SORTABLE_COLUMNS = {
    "created_at": models.Order.created_at,
    "name": models.Order.name,
    "customer": models.Order.customer,
    "financial_status": models.Order.financial_status,
    "total_price": models.Order.total_price,
}
ITEMS_PER_PAGE = 50


@router.get("/", response_class=HTMLResponse, name="view_orders")
async def get_orders(
    request: Request,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db), # Folosim AsyncSession deoarece funcția este 'async'
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    stores=Depends(get_stores_from_db),
    unfulfilled_count=Depends(get_unfulfilled_orders_count),
    unprinted_count=Depends(get_unprinted_orders_count),
    # Adaugă aici și alți parametri de filtrare de care ai nevoie (ex: store_id, search_query)
):
    """
    Afișează pagina principală a comenzilor cu paginare și sortare.
    """
    # Pas 1: Construiește interogarea de bază cu eager loading
    query = select(models.Order).options(
        selectinload(models.Order.shipments),
        selectinload(models.Order.store)
    )

    # Aici poți adăuga filtrele (ex: după magazin, status, etc.)
    # if store_id:
    #     query = query.where(models.Order.store_id == store_id)

    # Pas 2: Calculează numărul total de comenzi care corespund filtrelor
    count_query = select(func.count()).select_from(query.subquery())
    total_orders_result = await db.execute(count_query)
    total_orders = total_orders_result.scalar_one()

    # Pas 3: Calculează numărul total de pagini
    total_pages = (total_orders + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    # Pas 4: Aplică sortarea la interogarea principală
    if sort_by in SORTABLE_COLUMNS:
        column = SORTABLE_COLUMNS[sort_by]
        if sort_order == "asc":
            query = query.order_by(asc(column))
        else:
            query = query.order_by(desc(column))
    else:
        # Sortare implicită
        query = query.order_by(desc(models.Order.created_at))

    # Pas 5: Aplică paginarea și execută interogarea pentru a obține comenzile
    query = query.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    result = await db.execute(query)
    orders = result.scalars().all()

    # NOTĂ: Logica de 'filter_counts' și 'store_counts' nu poate funcționa
    # corect cu paginare, deoarece ar număra doar comenzile de pe pagina curentă.
    # Aceste numere ar trebui calculate prin interogări separate la BD, similar
    # cu 'unfulfilled_count' și 'unprinted_count'.
    
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
            "page": page,
            "total_orders": total_orders, # Variabila lipsă
            "total_pages": total_pages,   # Variabila lipsă
            "current_sort_by": sort_by,
            "current_sort_order": sort_order,
            "filter_counts": {}, # Trimitem un dicționar gol pentru a evita erori
        },
    )