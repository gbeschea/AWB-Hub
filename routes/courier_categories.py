# routes/courier_categories.py
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import models
from database import get_db
from dependencies import get_templates

router = APIRouter(prefix='/courier-categories', tags=['Courier Categories'])

@router.get('', response_class=HTMLResponse)
async def get_courier_categories_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates)
):
    categories_res = await db.execute(select(models.CourierCategory).order_by(models.CourierCategory.name))
    categories = categories_res.scalars().all()
    distinct_couriers_res = await db.execute(select(models.Shipment.courier).distinct())
    distinct_couriers = sorted([c[0] for c in distinct_couriers_res if c[0]])
    mappings_res = await db.execute(select(models.courier_category_map))
    mappings = mappings_res.all()
    category_map = {}
    for cat_id, courier_key in mappings:
        category_map.setdefault(cat_id, set()).add(courier_key)
    for cat in categories:
        cat.mapped_couriers = category_map.get(cat.id, set())
    return templates.TemplateResponse("courier_categories.html", {"request": request, "categories": categories, "distinct_couriers": distinct_couriers})

@router.post('', response_class=RedirectResponse)
async def create_courier_category(name: str = Form(...), db: AsyncSession = Depends(get_db)):
    existing_cat = await db.execute(select(models.CourierCategory).where(models.CourierCategory.name == name))
    if name.strip() and not existing_cat.scalar_one_or_none():
        db.add(models.CourierCategory(name=name))
        await db.commit()
    return RedirectResponse(url="/courier-categories", status_code=303)

@router.post('/assign', response_class=RedirectResponse)
async def assign_couriers_to_categories(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    
    # Salvează template-urile de URL
    all_categories_res = await db.execute(select(models.CourierCategory))
    all_categories = all_categories_res.scalars().all()
    for cat in all_categories:
        template_url = form_data.get(f"template_url_{cat.id}")
        cat.tracking_url_template = template_url if template_url and template_url.strip() else None
    
    # Salvează mapările curierilor
    await db.execute(models.courier_category_map.delete())
    new_mappings = []
    all_category_ids = {int(k.split('_')[1]) for k in form_data.keys() if k.startswith('couriers_')}
    for cat_id in all_category_ids:
        for key in form_data.getlist(f"couriers_{cat_id}"):
            new_mappings.append({'category_id': cat_id, 'courier_key': key})
    if new_mappings:
        # Se folosește .values() pentru inserare, dar deoarece e asincron, s-ar putea să necesite o abordare diferită
        # Pentru moment, păstrăm logica existentă care ar trebui să fie compatibilă
        await db.execute(models.courier_category_map.insert().values(new_mappings))

    await db.commit()
    return RedirectResponse(url="/courier-categories", status_code=303)

@router.post('/{category_id}/delete', response_class=RedirectResponse)
async def delete_courier_category(category_id: int, db: AsyncSession = Depends(get_db)):
    category = await db.get(models.CourierCategory, category_id)
    if category:
        await db.execute(models.courier_category_map.delete().where(models.courier_category_map.c.category_id == category_id))
        await db.delete(category)
        await db.commit()
    return RedirectResponse(url="/courier-categories", status_code=303)