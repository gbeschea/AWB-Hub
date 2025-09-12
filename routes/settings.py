# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/routes/settings.py

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
    pii_source_options = ['shopify', 'metafield']
    return templates.TemplateResponse("settings_stores.html", {"request": request, "stores": stores, "pii_source_options": pii_source_options})

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
    is_active: str = Form(...),
    pii_source: str = Form(...),
    paper_size: str = Form(...),
    dpd_client_id: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    """Actualizează un magazin existent."""
    is_active_bool = is_active.lower() == 'true'
    await crud_stores.update_store(
        db,
        store_id=store_id,
        name=name,
        domain=domain,
        shared_secret=shared_secret,
        access_token=access_token,
        is_active=is_active_bool,
        pii_source=pii_source,
        # AICI ERAU VIRGULELE LIPSĂ
        paper_size=paper_size,
        dpd_client_id=dpd_client_id
    )
    return RedirectResponse(url="/settings/stores", status_code=303)