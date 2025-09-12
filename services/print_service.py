import io
import logging
from typing import List, Tuple
from collections import defaultdict
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from itertools import groupby
import models
from services import label_service
from settings import settings

try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'DejaVuSans-Bold.ttf'))
    FONT_NAME, FONT_NAME_BOLD = 'DejaVuSans', 'DejaVuSans-Bold'
except Exception:
    logging.warning("Fontul DejaVuSans nu a fost găsit.")
    FONT_NAME, FONT_NAME_BOLD = 'Helvetica', 'Helvetica-Bold'

def _create_summary_page(info_lines: List[str]) -> io.BytesIO:
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A6)
    width, height = A6
    p.setFont(FONT_NAME_BOLD, 24)
    p.drawString(15 * mm, height - 20 * mm, info_lines[0])
    p.setFont(FONT_NAME, 11)
    y_position = height - 35 * mm
    for line in info_lines[1:]:
        p.drawString(15 * mm, y_position, line)
        y_position -= 7 * mm
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer


# services/print_service.py

# ... (păstrează toate importurile și funcția _create_summary_page neschimbate) ...

async def generate_pdf_for_selected_batches(db: AsyncSession, category_id: int, batch_numbers: List[int]) -> Tuple[io.BytesIO, List[str], List[str]]:
    batch_size = settings.PRINT_BATCH_SIZE
    
    # Pas 1: Preluare Store ID-uri (neschimbat)
    store_ids_res = await db.execute(
        select(models.store_category_map.c.store_id)
        .where(models.store_category_map.c.category_id == category_id)
    )
    store_ids_result = store_ids_res.scalars().all()
    if not store_ids_result:
        return io.BytesIO(), [], []

    # Pas 2: Preluare comenzi neprintate (neschimbat)
    latest_shipment_subq = (
        select(models.Shipment.order_id, func.max(models.Shipment.id).label("max_id"))
        .group_by(models.Shipment.order_id).alias("latest_shipment_subq")
    )
    supported_couriers_filter = or_(models.Shipment.courier.ilike('%dpd%'), models.Shipment.courier.ilike('%sameday%'))
    
    base_query = (
        select(models.Order)
        .join(models.Shipment, models.Order.id == models.Shipment.order_id)
        .join(latest_shipment_subq, models.Shipment.id == latest_shipment_subq.c.max_id)
        .options(
            selectinload(models.Order.store).selectinload(models.Store.categories), 
            selectinload(models.Order.line_items), 
            selectinload(models.Order.shipments)
        )
        .where(
            models.Order.store_id.in_(store_ids_result), 
            models.Shipment.printed_at.is_(None), 
            models.Shipment.awb.isnot(None), 
            supported_couriers_filter
        )
    )
    all_printable_orders_res = await db.execute(base_query)
    all_printable_orders = all_printable_orders_res.unique().scalars().all()

    # --- MODIFICARE: Pas 3 & 4 - Procesare și creare chei de sortare avansate ---
    processed_orders = []
    for order in all_printable_orders:
        latest_shipment = max(order.shipments, key=lambda s: s.id, default=None)
        if not latest_shipment or not latest_shipment.awb:
            continue

        category_name = "Necategorizat"
        if order.store and order.store.categories:
            category_name = order.store.categories[0].name

        # Calculăm noile atribute necesare pentru sortarea complexă
        unique_skus = {li.sku for li in order.line_items if li.sku}
        unique_sku_count = len(unique_skus)
        is_single_sku_order = unique_sku_count == 1
        
        # Sortăm produsele pentru a crea o "amprentă" consistentă
        sorted_line_items = sorted(order.line_items, key=lambda li: li.sku or "ZZZ")
        
        processed_orders.append({
            "order_object": order,
            "awb": latest_shipment.awb,
            "courier": latest_shipment.courier,
            "account_key": latest_shipment.account_key,
            # Chei pentru noua sortare ierarhică
            "sort_category": category_name,
            "sort_courier": latest_shipment.courier,
            "sort_unique_sku_count": unique_sku_count,
            "sort_is_single_sku": is_single_sku_order,
            "sort_single_sku_quantity": sorted_line_items[0].quantity if is_single_sku_order else 999,
            "sort_product_signature": ";".join([f"{li.quantity}x{li.sku}" for li in sorted_line_items]),
            "sort_first_sku": sorted_line_items[0].sku or "ZZZ",
            "sort_total_items": sum(li.quantity for li in order.line_items),
        })

    # Aplicăm noua sortare multi-nivel
    all_orders_sorted = sorted(
        processed_orders, 
        key=lambda o: (
            o['sort_category'],             # 1. Grupează după Categorie magazin
            o['sort_courier'],              # 2. Grupează după Curier
            o['sort_unique_sku_count'],     # 3. Sortează după nr. de produse unice (1, 2, 3...)
            
            # 4. Logică specială pentru comenzile cu un singur tip de produs
            o['sort_first_sku'] if o['sort_is_single_sku'] else 'ZZZ_fallback',
            o['sort_single_sku_quantity'] if o['sort_is_single_sku'] else 999,

            # 5. Logică pentru comenzile cu produse multiple
            o['sort_product_signature'],    # Grupează comenzile cu conținut identic
            -o['sort_total_items'],         # Fallback: sortează după cantitatea totală (desc)
        )
    )
    # --- SFÂRȘIT MODIFICARE ---
    
    # Pas 5: Selectarea loturilor (neschimbat)
    orders_in_selected_batches = []
    for batch_num in batch_numbers:
        start_index = (batch_num - 1) * batch_size
        end_index = batch_num * batch_size
        orders_in_selected_batches.extend(all_orders_sorted[start_index:end_index])
    
    if not orders_in_selected_batches:
        return io.BytesIO(), [], []

    # Pas 6 & 7: Generarea și asamblarea PDF-ului (neschimbat)
    shipments_to_fetch = [
        {"awb": o["awb"], "courier": o["courier"], "account_key": o["account_key"]} 
        for o in orders_in_selected_batches
    ]
    # Am redenumit funcția pentru a fi consistentă cu ce am folosit în `labels.py`
    awb_to_pdf_map, failed_awbs_dict = await label_service.generate_labels_pdf_sequentially(db, shipments_to_fetch)
    
    successful_awbs = list(awb_to_pdf_map.keys())
    failed_awbs = list(failed_awbs_dict.keys())
    
    if not successful_awbs:
        return io.BytesIO(), [], [s['awb'] for s in orders_in_selected_batches]

    final_pdf_writer = PdfWriter()
    for order_data in orders_in_selected_batches:
        awb = order_data['awb']
        if pdf_buffer := awb_to_pdf_map.get(awb):
            try:
                pdf_reader = PdfReader(pdf_buffer)
                for page in pdf_reader.pages:
                    final_pdf_writer.add_page(page)
            except Exception as e:
                logging.error(f"Eroare la adăugarea PDF pentru AWB {awb}: {e}")

    final_buffer = io.BytesIO()
    if len(final_pdf_writer.pages) > 0:
        final_pdf_writer.write(final_buffer)
    final_buffer.seek(0)
    
    return final_buffer, successful_awbs, failed_awbs

