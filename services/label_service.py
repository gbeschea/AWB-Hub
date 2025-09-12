import asyncio
import logging
from typing import List, Dict, Tuple
import io
from .couriers import get_courier_service

async def generate_labels_pdf(
    shipments_data: List[Dict]
) -> Tuple[Dict[str, io.BytesIO], Dict[str, str]]:
    """
    Generează etichete PDF, aplicând rate-limiting pentru Sameday.
    """
    if not shipments_data:
        return {}, {}

    awb_to_pdf_map: Dict[str, io.BytesIO] = {}
    failed_awbs_map: Dict[str, str] = {}
    
    sameday_shipments = [s for s in shipments_data if 'sameday' in s.get('courier', '').lower()]
    other_shipments = [s for s in shipments_data if 'sameday' not in s.get('courier', '').lower()]

    # --- PROCESARE PARALELĂ PENTRU DPD, ECONT ETC. ---
    other_sem = asyncio.Semaphore(10)
    async def other_worker(shipment: Dict):
        awb, courier, account = shipment.get('awb'), shipment.get('courier'), shipment.get('account_key')
        courier_service = get_courier_service(courier)
        if not courier_service: return
        async with other_sem:
            response = await courier_service.get_label(awb, account, 'A6')
            if response.success: awb_to_pdf_map[awb] = response.content
            else: failed_awbs_map[awb] = response.error_message

    # --- PROCESARE SECVENȚIALĂ CU PAUZĂ PENTRU SAMEDAY ---
    sameday_sem = asyncio.Semaphore(1)
    async def sameday_worker(shipment: Dict):
        awb, courier, account = shipment.get('awb'), shipment.get('courier'), shipment.get('account_key')
        courier_service = get_courier_service(courier)
        if not courier_service: return
        async with sameday_sem:
            await asyncio.sleep(1.0) # PAUZA DE 1 SECUNDĂ
            response = await courier_service.get_label(awb, account, 'A6')
            if response.success: awb_to_pdf_map[awb] = response.content
            else: failed_awbs_map[awb] = response.error_message

    other_tasks = [other_worker(s) for s in other_shipments]
    sameday_tasks = [sameday_worker(s) for s in sameday_shipments]
    
    await asyncio.gather(*(other_tasks + sameday_tasks))

    return awb_to_pdf_map, failed_awbs_map