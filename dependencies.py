# gbeschea/awb-hub/AWB-Hub-28035206bac3a3437048d87acde55b68d0fb6085/dependencies.py

# Importurile necesare, inclusiv Depends
from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
import models
from database import get_db
from fastapi.templating import Jinja2Templates
from zoneinfo import ZoneInfo
from datetime import datetime



templates = Jinja2Templates(directory="templates")

ROMANIA_TZ = ZoneInfo("Europe/Bucharest")

templates = Jinja2Templates(directory="templates") # Definim templates aici

def to_local_time(utc_dt: datetime):
    if utc_dt is None:
        return None
    return utc_dt.astimezone(ROMANIA_TZ)

# ADAUGĂ ACEASTĂ LINIE PENTRU A ÎNREGISTRA FILTRUL
templates.env.filters["localtime"] = to_local_time


async def get_stores_from_db(db: AsyncSession = Depends(get_db)):
    """
    Preia toate magazinele din baza de date, sortate după nume.
    """
    result = await db.execute(select(models.Store).order_by(models.Store.name))
    stores = result.scalars().all()
    return stores

async def get_unfulfilled_orders_count(db: AsyncSession = Depends(get_db)) -> int:
    """
    Numără comenzile care nu sunt încă "fulfilled" în Shopify.
    """
    count_result = await db.execute(
        select(func.count(models.Order.id))
        .where(models.Order.shopify_status != 'fulfilled')
    )
    count = count_result.scalar_one_or_none()
    return count or 0

async def get_unprinted_orders_count(db: AsyncSession = Depends(get_db)) -> int:
    """
    Numără transporturile care au fost create dar nu au încă eticheta printată.
    """
    count_result = await db.execute(
        select(func.count(models.Shipment.id))
        .where(models.Shipment.printed_at.is_(None))
    )
    count = count_result.scalar_one_or_none()
    return count or 0