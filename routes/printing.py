# routes/printing.py
import logging
import math
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, or_
from starlette.background import BackgroundTasks
import models
from database import get_db
from services import print_service
from background import update_shopify_in_background
from dependencies import get_templates
from settings import settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# --- AICI ESTE MODIFICAREA ---
# Am adăugat `name="print_view"` pentru a-i da rutei un nume explicit.
@router.get("/print-view", response_class=HTMLResponse, name="print_view")
async def get_print_view_page(request: Request, db: AsyncSession = Depends(get_db), templates: Jinja2Templates = Depends(get_templates)):
    # ... restul funcției rămâne neschimbat ...
    latest_shipment_subq = (select(models.Shipment.order_id, func.max(models.Shipment.id).label("max_id")).group_by(models.Shipment.order_id).alias("latest_shipment_subq"))
    supported_couriers_filter = or_(models.Shipment.courier_key.ilike('%dpd%'), models.Shipment.courier_key.ilike('%sameday%'))
    unprinted_counts_query = (
        select(models.StoreCategory.id, func.count(models.Order.id.distinct()))
        .join(models.store_category_map).join(models.Store).join(models.Order)
        .join(models.Shipment, models.Order.id == models.Shipment.order_id)
        .join(latest_shipment_subq, models.Shipment.id == latest_shipment_subq.c.max_id)
        .where(models.Shipment.printed_at.is_(None), models.Shipment.awb.isnot(None), supported_couriers_filter)
        .group_by(models.StoreCategory.id)
    )
    counts_res = await db.execute(unprinted_counts_query)
    counts_dict = dict(counts_res.all())
    categories_res = await db.execute(select(models.StoreCategory).order_by(models.StoreCategory.name))
    categories = categories_res.scalars().all()
    
    total_unprinted = 0
    batch_size = settings.PRINT_BATCH_SIZE
    for cat in categories:
        count = counts_dict.get(cat.id, 0)
        cat.unprinted_count = count
        cat.total_batches = math.ceil(count / batch_size) if count > 0 else 0
        total_unprinted += count
        
    return templates.TemplateResponse("print_view.html", {"request": request, "categories": categories, "total_unprinted": total_unprinted})

