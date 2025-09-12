# gbeschea/awb-hub/AWB-Hub-2de5efa965cc539c6da369d4ca8f3d17a4613f7f/settings.py

from pydantic_settings import BaseSettings
from typing import List, Dict, Any
import json
from pathlib import Path

# Linia de mai jos a fost ștearsă pentru a rezolva eroarea de import circular
# from database import get_db 

def json_config_settings_source(settings: BaseSettings) -> Dict[str, Any]:
    """
    O sursă de setări care încarcă variabile dintr-un fișier JSON
    specificat în câmpul `config_file` al modelului de setări.
    """
    config_file = getattr(settings.__class__.model_config, 'config_file', None)
    if config_file:
        config_path = Path(config_file)
        if config_path.is_file():
            return json.loads(config_path.read_text('utf-8'))
    return {}

class Settings(BaseSettings):
    DATABASE_URL: str
    SHOPIFY_STORES: List[Dict[str, Any]]
    COURIER_MAP: Dict[str, str]
    PAYMENT_MAP: Dict[str, List[str]]
    COURIER_STATUS_MAP: Dict[str, Dict[str, List[str]]]
    SAMEDAY_CONFIG: Dict[str, Any]
    DPD_CONFIG: Dict[str, Any]
    ECONT_CONFIG: Dict[str, Any]
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SYNC_INTERVAL_ORDERS_MINUTES: int = 15
    SYNC_INTERVAL_COURIERS_MINUTES: int = 5
    CORS_ORIGINS: List[str] = ["*"]
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        config_file = 'config/shopify_stores.json'
        
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

# Încarcă și mapează datele suplimentare din fișierele JSON
def load_json_config(file_path: str) -> Dict:
    path = Path(file_path)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

settings.COURIER_MAP = load_json_config('config/courier_map.json')
settings.PAYMENT_MAP = load_json_config('config/payment_map.json')
settings.COURIER_STATUS_MAP = load_json_config('config/courier_status_map.json')
settings.SHOPIFY_STORES = load_json_config('config/shopify_stores.json')
settings.SAMEDAY_CONFIG = load_json_config('config/sameday.json')
settings.DPD_CONFIG = load_json_config('config/dpd.json')
settings.ECONT_CONFIG = load_json_config('config/econt.json')