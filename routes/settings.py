import json
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from starlette.datastructures import FormData

from database import get_db
from models import Store, CourierAccount

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse, name="settings_page")
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@router.get("/stores", response_class=HTMLResponse, name="get_stores_settings")
async def get_stores_settings(request: Request, db: AsyncSession = Depends(get_db)):
    stores_result = await db.execute(select(Store))
    stores = stores_result.scalars().all()
    return templates.TemplateResponse("settings_stores.html", {"request": request, "stores": stores})

@router.post("/stores/add", name="add_new_store")
async def add_new_store(
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    domain: str = Form(...),
    access_token: str = Form(...),
    api_version: str = Form(...),
    shared_secret: str = Form(...),
    webhook_url: str = Form(None),
    pii_source: str = Form(...)
):
    new_store = Store(
        name=name, domain=domain, access_token=access_token, api_version=api_version,
        shared_secret=shared_secret, webhook_url=webhook_url, pii_source=pii_source
    )
    db.add(new_store)
    await db.commit()
    return RedirectResponse(url="/settings/stores", status_code=303)

@router.get("/couriers", response_class=HTMLResponse, name="get_couriers_settings")
async def get_couriers_settings(request: Request, db: AsyncSession = Depends(get_db)):
    couriers_result = await db.execute(select(CourierAccount))
    couriers = couriers_result.scalars().all()
    return templates.TemplateResponse("settings_couriers.html", {"request": request, "couriers": couriers})

# --- FUNCȚIA NOUĂ ADĂUGATĂ PENTRU CURIERI ---
@router.post("/couriers/add", name="add_new_courier")
async def add_new_courier(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Procesează formularul dinamic și adaugă un cont nou de curier.
    """
    form_data = await request.form()
    account_key = form_data.get("account_key")
    courier_key = form_data.get("courier_key")
    
    # Colectează dinamic toate câmpurile de credențiale
    credentials = {}
    for key, value in form_data.items():
        if key.startswith("credentials[") and key.endswith("]"):
            # Extrage numele câmpului, ex: 'username' din 'credentials[username]'
            cred_key = key[12:-1] 
            credentials[cred_key] = value

    new_courier_account = CourierAccount(
        account_key=account_key,
        courier_key=courier_key,
        credentials=credentials  # SQLAlchemy va serializa dicționarul în JSON
    )
    db.add(new_courier_account)
    await db.commit()

    return RedirectResponse(url="/settings/couriers", status_code=303)