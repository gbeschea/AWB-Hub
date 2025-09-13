from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from models import Order, PiiData

def apply_filters(filters: dict):
    """
    Construiește o interogare SQLAlchemy asincronă (folosind select)
    bazată pe filtrele primite.
    """
    # Începem cu o declarație SELECT
    query = select(Order).options(
        joinedload(Order.pii_data), 
        joinedload(Order.store)
    )

    # Alătură tabela PiiData dacă este necesară o căutare text
    if filters.get("search"):
        query = query.join(PiiData, Order.order_number == PiiData.order_number)

    # Aplică filtrele unul câte unul
    if filters.get("store_id"):
        query = query.where(Order.store_id == filters["store_id"])
    
    if filters.get("fulfillment_status"):
        query = query.where(Order.fulfillment_status == filters["fulfillment_status"])

    if filters.get("payment_status"):
        query = query.where(Order.financial_status == filters["payment_status"])

    if search_term := filters.get("search"):
        query = query.where(
            or_(
                PiiData.customer_name.ilike(f"%{search_term}%"),
                PiiData.customer_phone.ilike(f"%{search_term}%"),
                Order.order_number.ilike(f"%{search_term}%")
            )
        )

    # Aplică sortarea
    sort_by = filters.get("sort_by", "order_date")
    sort_dir = filters.get("sort_dir", "desc")
    
    sort_column = getattr(Order, sort_by, Order.order_date)
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    return query