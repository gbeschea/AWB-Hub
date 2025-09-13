# routes/validation.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from services.address_service import get_all_unvalidated_orders
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def get_validation_page(request: Request, db: Session = Depends(get_db)):
    orders = get_all_unvalidated_orders(db)
    return templates.TemplateResponse("validation.html", {"request": request, "orders": orders})


@router.post("/{order_id}/mark-valid", response_class=JSONResponse)
async def mark_order_as_valid(order_id: int, db: AsyncSession = Depends(get_db)):
    order = await db.get(models.Order, order_id)
    if not order:
        return JSONResponse(content={"error": "Comanda nu a fost găsită"}, status_code=404)
    
    order.address_status = 'valid'
    # Odată ce e validă, e gata de procesare
    order.processing_status = 'ready_for_processing' 
    await db.commit()
    
    return {"message": f"Comanda {order.name} a fost marcată ca validă."}


@router.post("/{order_id}/hold", response_class=JSONResponse)
async def hold_order(order_id: int, db: AsyncSession = Depends(get_db)):
    order = await db.get(models.Order, order_id)
    if not order:
        return JSONResponse(content={"error": "Comanda nu a fost găsită"}, status_code=404)
        
    order.processing_status = 'on_hold'
    await db.commit()
    
    # TODO: Adaugă un background task pentru a notifica Shopify cu o notă
    
    return {"message": f"Comanda {order.name} a fost pusă pe hold."}

# Model pentru a primi datele de adresă de la frontend
class AddressUpdate(BaseModel):
    field: str
    value: str

@router.patch("/{order_id}/address", response_class=JSONResponse)
async def update_address_field(order_id: int, update: AddressUpdate, db: AsyncSession = Depends(get_db)):
    order = await db.get(models.Order, order_id)
    if not order:
        return JSONResponse(content={"error": "Comanda nu a fost găsită"}, status_code=404)

    # Verificăm dacă field-ul este unul valid pentru a preveni erori
    if hasattr(order, update.field):
        setattr(order, update.field, update.value)
    else:
        return JSONResponse(content={"error": "Câmp invalid"}, status_code=400)

    # Re-validăm adresa după modificare
    from services.address_service import validate_address_for_order
    await validate_address_for_order(db, order)
    
    await db.commit()
    
    # TODO: Adaugă un background task pentru a actualiza adresa în Shopify
    
    return {
        "message": "Adresa a fost actualizată.",
        "new_status": order.address_status,
        "new_score": order.address_score,
        "new_errors": order.address_validation_errors,
    }

@router.post("/re-validate-all", response_class=JSONResponse, name="re_validate_all_invalid")
async def re_validate_all_invalid_orders(db: AsyncSession = Depends(get_db)):
    """
    Ia toate comenzile cu status 'invalid' și le re-rulează prin validator.
    Perfect pentru a testa rapid modificările aduse logicii de validare.
    """
    invalid_orders_query = select(models.Order).where(models.Order.address_status == 'invalid')
    result = await db.execute(invalid_orders_query)
    orders_to_revalidate = result.scalars().all()

    count = 0
    for order in orders_to_revalidate:
        await validate_address_for_order(db, order)
        count += 1
    
    await db.commit()

    return {"message": f"{count} de comenzi au fost re-validate."}
