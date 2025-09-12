from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import Session
import models

async def get_stores(db: AsyncSession):
    """Preia toate magazinele din baza de date."""
    result = await db.execute(select(models.Store).order_by(models.Store.name))
    return result.scalars().all()

async def create_store(db: AsyncSession, name: str, domain: str, shared_secret: str, access_token: str):
    """Creează un magazin nou."""
    new_store = models.Store(
        name=name, 
        domain=domain, 
        shared_secret=shared_secret, 
        access_token=access_token, 
        is_active=True
    )
    db.add(new_store)
    await db.commit()
    return new_store

async def update_store(db: AsyncSession, store_id: int, name: str, domain: str, shared_secret: str, access_token: str, is_active: bool):
    """Actualizează detaliile unui magazin existent."""
    stmt = (
        update(models.Store)
        .where(models.Store.id == store_id)
        .values(
            name=name, 
            domain=domain, 
            shared_secret=shared_secret, 
            access_token=access_token, 
            is_active=is_active
        )
    )
    await db.execute(stmt)
    await db.commit()