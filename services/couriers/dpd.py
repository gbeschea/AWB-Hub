import io
import json
from typing import Optional
from datetime import datetime
from .base import BaseCourier, LabelResponse, TrackingResponse
from settings import settings

API_BASE_DPD = 'https://api.dpd.ro/v1'

class DPDCourier(BaseCourier):
    async def get_label(self, awb: str, account_key: Optional[str], paper_size: str) -> LabelResponse:
        creds = settings.DPD_CREDS.get(account_key)
        if not creds:
            return LabelResponse(success=False, error_message=f"Nu s-au găsit credențiale DPD pentru contul: {account_key}")

        body = {'userName': creds['username'], 'password': creds['password'], 'paperSize': paper_size, 'parcels': [{'parcel': {'id': awb}}]}
        try:
            r = await self.client.post(f'{API_BASE_DPD}/print', json=body, timeout=45)
            
            if r.status_code == 200 and 'application/pdf' in r.headers.get('content-type', ''):
                return LabelResponse(success=True, content=io.BytesIO(r.content))
            
            try:
                error_msg = r.json().get('error', {}).get('message', 'Răspuns necunoscut')
            except json.JSONDecodeError:
                error_msg = "Răspuns neașteptat de la DPD (HTML sau text primit în loc de PDF)."
            
            return LabelResponse(success=False, error_message=f"Eroare DPD: {error_msg}")
            
        except Exception as e:
            return LabelResponse(success=False, error_message=f"Excepție la generare etichetă DPD: {e}")

    async def track_awb(self, awb: str, account_key: Optional[str]) -> TrackingResponse:
        creds = settings.DPD_CREDS.get(account_key)
        if not creds:
            return TrackingResponse(status='Cont Necunoscut', date=None)

        body = {'userName': creds['username'], 'password': creds['password'], 'language': 'EN', 'parcels': [{'id': awb}]}
        try:
            r = await self.client.post(f'{API_BASE_DPD}/track/', json=body, timeout=15.0)
            if r.status_code != 200:
                return TrackingResponse(status=f'HTTP {r.status_code}', date=None)
            
            data = (r.json() or {}).get('parcels', [{}])[0]
            operations = data.get('operations', [])
            last_op = operations[-1] if operations else {}
            last_desc = (last_op.get('description') or 'N/A').strip()
            last_dt = datetime.fromisoformat(last_op['date'].replace('Z', '+00:00')) if last_op.get('date') else None
            return TrackingResponse(status=last_desc, date=last_dt, raw_data=data)
        except Exception:
            return TrackingResponse(status='Eroare API', date=None)