# routes/sync.py
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from services.sync_service import sync_all_stores

router = APIRouter()

@router.post("/all", response_class=RedirectResponse)
async def sync_all_stores_route(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    background_tasks.add_task(sync_all_stores, db)
    # This is a background task, so we redirect immediately.
    # A flash message could be added to inform the user.
    return RedirectResponse(url="/", status_code=303)

async def run_sync_task(request: Request, sync_function, db: AsyncSession, *args, **kwargs):
    request.app.state.is_syncing = True
    try:
        await sync_function(db, *args, **kwargs)
    except Exception as e:
        logging.error(f"Eroare în timpul task-ului de sincronizare: {e}", exc_info=True)
        await manager.broadcast({"type": "sync_error", "message": "A apărut o eroare."})
    finally:
        request.app.state.is_syncing = False

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@router.post('/orders')
async def sync_orders_start(request: Request, background_tasks: BackgroundTasks, days: int = Form(30), db: AsyncSession = Depends(get_db)):
    if request.app.state.is_syncing: return JSONResponse(status_code=409, content={"message": "O altă sincronizare este deja în curs."})
    background_tasks.add_task(run_sync_task, request, sync_service.run_orders_sync, db, days=days, full_sync=False)
    return JSONResponse(content={"ok": True, "message": "Sincronizarea comenzilor a pornit."})

@router.post('/couriers')
async def sync_couriers_start(request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    if request.app.state.is_syncing: return JSONResponse(status_code=409, content={"message": "O altă sincronizare este deja în curs."})
    background_tasks.add_task(run_sync_task, request, sync_service.run_couriers_sync, db, full_sync=False)
    return JSONResponse(content={"ok": True, "message": "Sincronizarea curierilor a pornit."})

@router.post('/full')
async def sync_full_start(request: Request, background_tasks: BackgroundTasks, days: int = Form(30), db: AsyncSession = Depends(get_db)):
    if request.app.state.is_syncing: return JSONResponse(status_code=409, content={"message": "O altă sincronizare este deja în curs."})
    background_tasks.add_task(run_sync_task, request, sync_service.run_full_sync, db, days=days)
    return JSONResponse(content={"ok": True, "message": "Sincronizarea totală a pornit."})