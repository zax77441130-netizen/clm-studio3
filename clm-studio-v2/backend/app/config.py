from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / 'data'
UPLOADS_DIR = DATA_DIR / 'uploads'
SITE_FILE = DATA_DIR / 'site.json'

class Settings(BaseSettings):
    app_name: str = 'CLM Studio V2 Backend'
    host: str = '127.0.0.1'
    port: int = 8200
    admin_token: str = 'c7s20230521'
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

settings = Settings()
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
