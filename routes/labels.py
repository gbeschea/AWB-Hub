# routes/labels.py
import io
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from sqlalchemy import select
from pypdf import PdfWriter, PdfReader
from starlette.background import BackgroundTasks

import models
from database import get_db
from services import label_service
from background import update_shopify_in_background

router = APIRouter(prefix='/labels', tags=['Labels'])

@router.post('/merge_for_print')
async def merge_labels_for_printing(request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    awbs_to_process = form_data.get("awbs").split(',') if form_data.get("awbs") else []
    if not awbs_to_process:
        return JSONResponse(content={'detail': 'Niciun AWB selectat'}, status_code=400)

    shipments_res = await db.execute(select(models.Shipment).where(models.Shipment.awb.in_(awbs_to_process)))
    shipments = shipments_res.scalars().all()
    shipments_data = [{"awb": s.awb, "courier": s.courier, "account_key": s.account_key} for s in shipments]
    
    # --- MODIFICARE AICI: Am corectat numele funcției și am scos argumentul 'db' ---
    awb_to_pdf_map, failed_awbs_map = await label_service.generate_labels_pdf(shipments_data)
    successful_awbs = list(awb_to_pdf_map.keys())

    if not successful_awbs:
        error_detail = "Nicio etichetă nu a putut fi generată."
        if failed_awbs_map:
            failed_list = ", ".join(failed_awbs_map.keys())
            error_detail += f" Următoarele AWB-uri au eșuat: {failed_list}"
        return JSONResponse(content={'detail': error_detail}, status_code=500)
    
    final_pdf_writer = PdfWriter()
    for awb in awbs_to_process:
        if pdf_buffer := awb_to_pdf_map.get(awb):
            try:
                pdf_reader = PdfReader(pdf_buffer)
                for page in pdf_reader.pages:
                    final_pdf_writer.add_page(page)
            except Exception as e:
                logging.error(f"Nu s-a putut procesa PDF-ul pentru AWB {awb}: {e}")

    final_buffer = io.BytesIO()
    if len(final_pdf_writer.pages) > 0:
        final_pdf_writer.write(final_buffer)
    final_buffer.seek(0)
    
    now = datetime.now(timezone.utc)
    shipments_to_mark_res = await db.execute(select(models.Shipment).where(models.Shipment.awb.in_(successful_awbs), models.Shipment.printed_at.is_(None)))
    shipments_to_mark = shipments_to_mark_res.scalars().all()
    for ship in shipments_to_mark:
        ship.printed_at = now
    
    await db.commit()
    
    background_tasks.add_task(update_shopify_in_background, successful_awbs)
    return StreamingResponse(final_buffer, media_type='application/pdf')

@router.get("/download/{awb}", name="download_single_label")
async def download_single_label(awb: str, db: AsyncSession = Depends(get_db)):
    shipment_res = await db.execute(select(models.Shipment).where(models.Shipment.awb == awb))
    shipment = shipment_res.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail=f"AWB-ul {awb} nu a fost găsit în baza de date.")

    shipment_data = [{"awb": shipment.awb, "courier": shipment.courier, "account_key": shipment.account_key}]
    
    # --- MODIFICARE AICI: Am corectat numele funcției și am scos argumentul 'db' ---
    awb_to_pdf_map, failed_awbs = await label_service.generate_labels_pdf(shipment_data)
    
    pdf_buffer = awb_to_pdf_map.get(awb)
    
    if not pdf_buffer:
        error_reason = failed_awbs.get(awb, "Curierul nu a răspuns sau AWB-ul este invalid.")
        error_html = f"""
        <html lang="ro" data-theme="light">
            <head>
                <title>Eroare AWB</title>
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css"/>
                <style> body {{ padding: 2rem; }} </style>
            </head>
            <body class="container">
                <article>
                    <h1>Eroare la Generarea Etichetei</h1>
                    <p>Nu s-a putut descărca eticheta pentru AWB-ul <strong>{awb}</strong>.</p>
                    <p><strong>Motiv raportat de curier:</strong> {error_reason}</p>
                    <a href="javascript:history.back()" role="button" class="secondary">Înapoi</a>
                </article>
            </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=404)
        
    headers = {'Content-Disposition': f'attachment; filename="AWB_{awb}.pdf"'}
    return StreamingResponse(pdf_buffer, media_type='application/pdf', headers=headers)