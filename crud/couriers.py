# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/crud/couriers.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import CourierAccount, CourierMapping
import json

async def get_courier_accounts(db: AsyncSession):
    result = await db.execute(select(CourierAccount).order_by(CourierAccount.name))
    return result.scalars().all()

async def get_courier_account(db: AsyncSession, account_id: int):
    result = await db.execute(select(CourierAccount).where(CourierAccount.id == account_id))
    return result.scalar_one_or_none()

async def create_courier_account(db: AsyncSession, name: str, account_key: str, courier_type: str, tracking_url: str, credentials: dict):
    new_account = CourierAccount(
        name=name, account_key=account_key, courier_type=courier_type,
        tracking_url=tracking_url, credentials=credentials
    )
    db.add(new_account)
    await db.commit()

# MODIFICARE AICI: Am corectat numele parametrului
async def update_courier_account(db: AsyncSession, account_id: int, name: str, account_key: str, courier_type: str, tracking_url: str, credentials: dict, is_active: bool):
    result = await db.execute(select(CourierAccount).where(CourierAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account:
        account.name = name
        account.account_key = account_key
        account.courier_type = courier_type
        account.tracking_url = tracking_url
        # Acum, această linie este corectă
        account.credentials = credentials 
        account.is_active = is_active
        await db.commit()

async def get_courier_mappings(db: AsyncSession):
    result = await db.execute(select(CourierMapping).order_by(CourierMapping.shopify_name))
    return result.scalars().all()

async def create_courier_mapping(db: AsyncSession, shopify_name: str, account_key: str):
    new_mapping = CourierMapping(shopify_name=shopify_name, account_key=account_key)
    db.add(new_mapping)
    await db.commit()