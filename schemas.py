from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class StoreBase(BaseModel):
    id: int
    name: str
    domain: str

class ShipmentBase(BaseModel):
    id: int
    awb: Optional[str]
    courier: Optional[str]
    last_status: Optional[str]

    class Config:
        orm_mode = True

class OrderRead(BaseModel):
    id: int
    name: str
    customer: str
    created_at: datetime
    total_price: Optional[float]
    mapped_payment: Optional[str]
    shopify_status: Optional[str]
    derived_status: Optional[str]
    processing_status: str
    assigned_courier: Optional[str]
    store: StoreBase
    shipments: List[ShipmentBase] = []

    class Config:
        orm_mode = True # Permite Pydantic să citească datele direct din obiecte SQLAlchemy
