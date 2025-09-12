# routes/settings.py

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from dependencies import get_templates
from crud import stores as crud_stores

router = APIRouter(prefix='/settings', tags=['Settings'])

@router.get('', response_class=HTMLResponse, name="get_settings_page")
async def get_settings_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Afișează pagina principală de setări, care acționează ca un hub."""
    return templates.TemplateResponse("settings.html", {"request": request})

@router.get('/stores', response_class=HTMLResponse, name="get_stores_page")
async def get_stores_page(request: Request, db: AsyncSession = Depends(get_db), templates: Jinja2Templates = Depends(get_templates)):
    """Afișează pagina de management al magazinelor."""
    stores = await crud_stores.get_stores(db)
    return templates.TemplateResponse("settings_stores.html", {"request": request, "stores": stores})

@router.post('/stores', response_class=RedirectResponse, name="create_store")
async def create_store_entry(
    name: str = Form(...),
    domain: str = Form(...),
    shared_secret: str = Form(...),
    access_token: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Creează un magazin nou."""
    await crud_stores.create_store(db, name=name, domain=domain, shared_secret=shared_secret, access_token=access_token)
    return RedirectResponse(url="/settings/stores", status_code=303)

@router.post('/stores/{store_id}', response_class=RedirectResponse, name="update_store")
async def update_store_entry(
    store_id: int,
    name: str = Form(...),
    domain: str = Form(...),
    shared_secret: str = Form(...),
    access_token: str = Form(...),
    # MODIFICARE AICI: Primește valoarea ca un string
    is_active: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    """Actualizează un magazin existent."""
    # MODIFICARE AICI: Convertește string-ul 'true' în boolean
    is_active_bool = is_active.lower() == 'true'
    await crud_stores.update_store(db, store_id=store_id, name=name, domain=domain, shared_secret=shared_secret, access_token=access_token, is_active=is_active_bool)
    return RedirectResponse(url="/settings/stores", status_code=303)
