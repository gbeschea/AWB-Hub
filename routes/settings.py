from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models import Store, CourierAccount

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# --- FUNCȚIA ADĂUGATĂ ---
@router.get("/", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    Afișează pagina principală de setări.
    """
    return templates.TemplateResponse("settings.html", {"request": request})
# -------------------------

@router.get("/stores", response_class=HTMLResponse)
async def get_stores_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Afișează pagina de setări pentru magazine.
    """
    stores_result = await db.execute(select(Store))
    stores = stores_result.scalars().all()
    return templates.TemplateResponse("settings_stores.html", {"request": request, "stores": stores})

@router.get("/couriers", response_class=HTMLResponse)
async def get_couriers_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Afișează pagina de setări pentru curieri.
    """
    couriers_result = await db.execute(select(CourierAccount))
    couriers = couriers_result.scalars().all()
    return templates.TemplateResponse("settings_couriers.html", {"request": request, "couriers": couriers})

# Aici poți adăuga endpoint-uri POST pentru a adăuga/modifica magazine și curieri