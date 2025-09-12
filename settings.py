# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/settings.py

from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import List, Dict, Any, Optional
import json
from pathlib import Path

class ShopifyStore(BaseModel):
    brand: str
    domain: str
    access_token: str # MODIFICAT: Am redenumit din 'api_key'
    shared_secret: str
    api_version: str = "2024-04"

def json_config_settings_source(settings: BaseSettings) -> Dict[str, Any]:
    return {}

class Settings(BaseSettings):
    DATABASE_URL: str
    
    COURIER_MAP: Optional[Dict[str, str]] = None
    PAYMENT_MAP: Optional[Dict[str, List[str]]] = None
    COURIER_STATUS_MAP: Optional[Dict[str, Dict[str, List[str]]]] = None
    SAMEDAY_CONFIG: Optional[Dict[str, Any]] = None
    DPD_CONFIG: Optional[Dict[str, Any]] = None
    ECONT_CONFIG: Optional[Dict[str, Any]] = None
    
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SYNC_INTERVAL_ORDERS_MINUTES: int = 15
    SYNC_INTERVAL_COURIERS_MINUTES: int = 5
    CORS_ORIGINS: List[str] = ["*"]

    print_batch_size: int = 250
    archive_retention_days: int = 7
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        
        @classmethod
        def customise_sources(
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ):
            return (
                init_settings,
                dotenv_settings,
                env_settings,
                file_secret_settings,
                json_config_settings_source,
            )

settings = Settings()

def load_json_config(file_path: str) -> Any:
    path = Path(file_path)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

settings.COURIER_MAP = load_json_config('config/courier_map.json')
settings.PAYMENT_MAP = load_json_config('config/payment_map.json')
settings.COURIER_STATUS_MAP = load_json_config('config/courier_status_map.json')
settings.SAMEDAY_CONFIG = load_json_config('config/sameday.json')
settings.DPD_CONFIG = load_json_config('config/dpd.json') 
settings.ECONT_CONFIG = load_json_config('config/econt.json')