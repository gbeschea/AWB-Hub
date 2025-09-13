from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Float, ForeignKey, Text, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# Baza declarativă pentru modelele SQLAlchemy
Base = declarative_base()

# -----------------
# MODELE PRINCIPALE
# -----------------

class Store(Base):
    """Definește un magazin Shopify conectat la aplicație."""
    __tablename__ = 'stores'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    domain = Column(String, unique=True, nullable=False)
    access_token = Column(String, nullable=False)
    api_version = Column(String, nullable=False)
    orders = relationship("Order", back_populates="store", cascade="all, delete-orphan")
    store_category_maps = relationship("StoreCategoryMap", back_populates="store", cascade="all, delete-orphan")
    store_courier_account_maps = relationship("StoreCourierAccountMap", back_populates="store", cascade="all, delete-orphan")

class Order(Base):
    """Stochează o comandă importată dintr-un magazin Shopify."""
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    shopify_order_id = Column(String, unique=True, nullable=False)
    order_number = Column(String, unique=True, nullable=False, index=True)
    store_id = Column(Integer, ForeignKey('stores.id'), nullable=False)
    financial_status = Column(String)
    fulfillment_status = Column(String)
    total_price = Column(Float)
    currency = Column(String)
    order_date = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    store = relationship("Store", back_populates="orders")
    pii_data = relationship("PiiData", uselist=False, back_populates="order", cascade="all, delete-orphan")
    shipments = relationship("Shipment", back_populates="order", cascade="all, delete-orphan")
    line_items = relationship("LineItem", back_populates="order", cascade="all, delete-orphan")

class PiiData(Base):
    """Stochează datele personale (PII) pentru comenzi."""
    __tablename__ = 'pii_data'
    order_number = Column(String, ForeignKey('orders.order_number'), primary_key=True)
    customer_name = Column(String)
    customer_phone = Column(String)
    customer_email = Column(String)
    shipping_address = Column(Text)
    order = relationship("Order", back_populates="pii_data")

class LineItem(Base):
    """Definește un produs dintr-o comandă."""
    __tablename__ = 'line_items'
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    shopify_line_item_id = Column(String, unique=True)
    product_id = Column(String)
    sku = Column(String, index=True)
    name = Column(String)
    quantity = Column(Integer)
    price = Column(Float)
    order = relationship("Order", back_populates="line_items")

class Shipment(Base):
    """Definește un AWB asociat unei comenzi."""
    __tablename__ = 'shipments'
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    awb = Column(String, unique=True, index=True)
    courier_key = Column(String)
    status = Column(String, default="new")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    order = relationship("Order", back_populates="shipments")

# ---------------------
# MODELE PENTRU CURIERI
# ---------------------

class CourierAccount(Base):
    """Stochează datele de autentificare pentru un cont de curier."""
    __tablename__ = 'courier_accounts'
    id = Column(Integer, primary_key=True)
    account_key = Column(String, unique=True, nullable=False)
    courier_key = Column(String, nullable=False)
    credentials = Column(JSON, nullable=False)
    store_courier_account_maps = relationship("StoreCourierAccountMap", back_populates="courier_account", cascade="all, delete-orphan")
    mappings = relationship("CourierMapping", back_populates="account")

class CourierMapping(Base):
    """Harta de valori specifice unui cont de curier (ex: ID serviciu)."""
    __tablename__ = 'courier_mappings'
    id = Column(Integer, primary_key=True)
    account_key = Column(String, ForeignKey('courier_accounts.account_key'))
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    account = relationship("CourierAccount", back_populates="mappings")

class CourierCategory(Base):
    """Definește o categorie de curier (ex: 'standard', 'express')."""
    __tablename__ = 'courier_categories'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

class CourierCategoryMap(Base):
    """Leagă un curier de o categorie."""
    __tablename__ = 'courier_category_map'
    category_id = Column(Integer, ForeignKey('courier_categories.id'), primary_key=True)
    courier_key = Column(String, primary_key=True)

class CourierStatusMappingRule(Base):
    """Definește reguli de mapare a statusurilor primite de la curieri."""
    __tablename__ = 'courier_status_mapping_rules'
    id = Column(Integer, primary_key=True)
    courier_key = Column(String, nullable=False, index=True)
    raw_status_keyword = Column(String, nullable=False)
    standardized_status = Column(String, nullable=False)

# -----------------------------
# MODELE DE CONFIGURARE MAGAZIN
# -----------------------------

class StoreCourierAccountMap(Base):
    """Leagă magazinele de conturile de curier."""
    __tablename__ = 'store_courier_account_map'
    store_id = Column(Integer, ForeignKey('stores.id'), primary_key=True)
    courier_account_id = Column(Integer, ForeignKey('courier_accounts.id'), primary_key=True)
    store = relationship("Store", back_populates="store_courier_account_maps")
    courier_account = relationship("CourierAccount", back_populates="store_courier_account_maps")

class StoreCategory(Base):
    """Definește o categorie în care poate fi încadrat un magazin."""
    __tablename__ = 'store_categories'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    store_category_maps = relationship("StoreCategoryMap", back_populates="category", cascade="all, delete-orphan")

class StoreCategoryMap(Base):
    """Leagă magazinele de categoriile de magazine."""
    __tablename__ = 'store_category_map'
    category_id = Column(Integer, ForeignKey('store_categories.id'), primary_key=True)
    store_id = Column(Integer, ForeignKey('stores.id'), primary_key=True)
    store = relationship("Store", back_populates="store_category_maps")
    category = relationship("StoreCategory", back_populates="store_category_maps")

# -----------------
# MODELE UTILITARE
# -----------------

class User(Base):
    """Definește un utilizator al aplicației."""
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

class SyncOperation(Base):
    """Înregistrează operațiunile de sincronizare a datelor."""
    __tablename__ = 'sync_operations'
    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, default=func.now())
    end_time = Column(DateTime)
    status = Column(String)
    details = Column(Text)

class PrintLog(Base):
    """Log general pentru o sesiune de printare."""
    __tablename__ = 'print_logs'
    id = Column(Integer, primary_key=True)
    print_time = Column(DateTime, default=func.now())
    user_id = Column(Integer, ForeignKey('users.id'))
    status = Column(String)
    entries = relationship("PrintLogEntry", back_populates="print_log", cascade="all, delete-orphan")

class PrintLogEntry(Base):
    """Detalii pentru fiecare AWB printat."""
    __tablename__ = 'print_log_entries'
    id = Column(Integer, primary_key=True)
    print_log_id = Column(Integer, ForeignKey('print_logs.id'))
    shipment_id = Column(Integer, ForeignKey('shipments.id'))
    status = Column(String)
    print_log = relationship("PrintLog", back_populates="entries")

class RomaniaAddress(Base):
    """Stochează adrese din România pentru validare."""
    __tablename__ = 'romania_addresses'
    id = Column(Integer, primary_key=True)
    county = Column(String)
    city = Column(String)
    locality = Column(String)
    street = Column(String)
    postal_code = Column(String)