# routes/sync.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Form, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTasks
from database import get_db
from services import sync_service
from websocket_manager import manager

router = APIRouter(prefix='/sync', tags=['Sync'])

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