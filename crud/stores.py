# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/crud/stores.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import Store

async def get_stores(db: AsyncSession):
    """Prelucrează toate magazinele din baza de date."""
    result = await db.execute(select(Store).order_by(Store.name))
    return result.scalars().all()

async def create_store(db: AsyncSession, name: str, domain: str, shared_secret: str, access_token: str):
    """Creează un magazin nou."""
    new_store = Store(name=name, domain=domain, shared_secret=shared_secret, access_token=access_token, is_active=True)
    db.add(new_store)
    await db.commit()
    await db.refresh(new_store)
    return new_store

# MODIFICAT: Am adăugat 'pii_source: str' în semnătura funcției
async def update_store(db: AsyncSession, store_id: int, name: str, domain: str, shared_secret: str, access_token: str, is_active: bool, pii_source: str):
    """Actualizează un magazin existent."""
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if store:
        store.name = name
        store.domain = domain
        if shared_secret: # Actualizează doar dacă este furnizat
            store.shared_secret = shared_secret
        if access_token: # Actualizează doar dacă este furnizat
            store.access_token = access_token
        store.is_active = is_active
        
        # ADĂUGAT: Salvăm noua valoare în baza de date
        store.pii_source = pii_source
        
        await db.commit()
        await db.refresh(store)
    return store