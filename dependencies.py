# dependencies.py
from fastapi import Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from datetime import datetime
from zoneinfo import ZoneInfo

import models
from database import get_db

ROMANIA_TZ = ZoneInfo("Europe/Bucharest")

def to_local_time(utc_dt: datetime):
    if utc_dt is None:
        return None
    return utc_dt.astimezone(ROMANIA_TZ)

async def get_flash_messages(request: Request) -> dict:
    """Retrieves and clears flash messages from the session."""
    messages = request.session.pop('flash_messages', [])
    return {"messages": messages}

async def get_stores_from_db(db: Session = Depends(get_db)):
    """Fetches all stores from the database."""
    result = await db.execute(select(models.Store).order_by(models.Store.name))
    return result.scalars().all()

async def get_unfulfilled_orders_count(db: Session = Depends(get_db)) -> int:
    """Counts orders that are not fulfilled or canceled."""
    query = select(func.count(models.Order.id)).where(
        models.Order.fulfillment_status.is_(None),
        models.Order.status != 'cancelled'
    )
    result = await db.execute(query)
    return result.scalar_one_or_none() or 0

async def get_unprinted_orders_count(db: Session = Depends(get_db)) -> int:
    """Counts orders that have not been printed."""
    query = select(func.count(models.Order.id)).where(models.Order.is_printed == False)
    result = await db.execute(query)
    return result.scalar_one_or_none() or 0

def get_pagination_numbers(current_page: int, total_pages: int, context_size: int = 2) -> list:
    """Generates a list of page numbers for pagination controls."""
    if total_pages <= 1:
        return []

    page_numbers = []
    start_page = max(1, current_page - context_size)
    end_page = min(total_pages, current_page + context_size)

    if start_page > 1:
        page_numbers.append(1)
        if start_page > 2:
            page_numbers.append('...')
    
    page_numbers.extend(range(start_page, end_page + 1))

    # --- START: CORRECTED INDENTATION ---
    if end_page < total_pages:
        if end_page < total_pages - 1:
            page_numbers.append('...')
        page_numbers.append(total_pages)
    # --- END: CORRECTED INDENTATION ---
        
    return page_numbers

# Note: The 'get_templates' function was removed as it's not being used and templates are initialized directly.