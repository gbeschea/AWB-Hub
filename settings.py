import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Modele pentru structurile de date din JSON-uri ---

class ShopifyStore(BaseModel):
    domain: str
    brand: str
    access_token: str
    api_version: str = "2024-04"

# --- Funcție pentru a încărca configurările din directorul /config ---

def json_config_settings_source() -> Dict[str, Any]:
    """
    Încarcă setările din fișierele .json din directorul /config.
    """
    # --- AICI ESTE CORECȚIA ---
    config_dir = Path(__file__).parent / 'config'
    config = {}
    
    def load_json(filename: str, key: str):
        filepath = config_dir / filename
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                config[key] = json.load(f)

    load_json('shopify_stores.json', 'SHOPIFY_STORES')
    load_json('dpd.json', 'DPD_CREDS')
    load_json('sameday.json', 'SAMEDAY_CREDS')
    load_json('econt.json', 'ECONT_CREDS')
    load_json('courier_map.json', 'COURIER_MAP')
    load_json('payment_map.json', 'PAYMENT_MAP')
    load_json('courier_status_map.json', 'COURIER_STATUS_MAP')
    load_json('sameday_id_delivered copy.json', 'SAMEDAY_DELIVERED_IDS')
    load_json('sameday_id_refused.json', 'SAMEDAY_RETURNED_IDS')

    if 'NOT_LEFT_STATUSES' not in config:
        config['NOT_LEFT_STATUSES'] = [
            "Preluat de la expeditor", 
            "Expedierea a fost preluata de catre curier", 
            "Received in Sameday warehouse", 
            "In procesare in depozitul Sameday", 
            "AWB issued"
        ]

    return config


# --- Clasa principală de Settings ---

class Settings(BaseSettings):
    # Setări încărcate direct din .env
    DATABASE_URL: str
    PRINT_BATCH_SIZE: int = 250
    ARCHIVE_RETENTION_DAYS: int = 7

    # Setări care vor fi populate de `json_config_settings_source`
    SHOPIFY_STORES: List[ShopifyStore] = []
    DPD_CREDS: Dict[str, Dict[str, str]] = {}
    SAMEDAY_CREDS: Dict[str, str] = {}
    ECONT_CREDS: Dict[str, str] = {}
    COURIER_MAP: Dict[str, str] = {}
    PAYMENT_MAP: Dict[str, List[str]] = {}
    COURIER_STATUS_MAP: Dict[str, Tuple[str, List[str]]] = {}
    SAMEDAY_DELIVERED_IDS: List[int] = []
    SAMEDAY_RETURNED_IDS: List[int] = []
    NOT_LEFT_STATUSES: List[str] = []

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore' # Ignoră variabilele extra din .env
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Definește ordinea de prioritate: .env are prioritate, apoi JSON-urile
        return (
            init_settings,
            dotenv_settings,
            env_settings,
            json_config_settings_source,
            file_secret_settings,
        )

settings = Settings()

