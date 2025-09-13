from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
# --- AICI ESTE MODIFICAREA ---
# Am schimbat 'sync_orders' în 'run_orders_sync'
from services.sync_service import run_orders_sync

router = APIRouter()

@router.post("/", name="run_sync")
async def run_sync(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Rulează sincronizarea comenzilor pentru ultimele 14 zile.
    """
    # --- AICI ESTE A DOUA MODIFICARE ---
    # Am actualizat și numele funcției apelate
    await run_orders_sync(db, days=14) 
    
    # Redirecționează utilizatorul înapoi la pagina principală
    return RedirectResponse(url="/", status_code=303)