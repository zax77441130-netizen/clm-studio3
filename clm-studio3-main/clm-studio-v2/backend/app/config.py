from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = 'CLM Studio V2 Backend'
    host: str = '127.0.0.1'
    port: int = 8200
    admin_token: str = Field(..., alias='ADMIN_TOKEN')
    environment: str = Field('development', alias='ENVIRONMENT')
    data_dir: str = Field(str(BASE_DIR / 'data'), alias='DATA_DIR')
    session_cookie_name: str = 'clm_admin_session'
    csrf_header_name: str = 'X-CSRF-Token'
    cookie_samesite: str = 'Lax'
    session_ttl_seconds: int = 8 * 60 * 60
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore', populate_by_name=True)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == 'production'

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser().resolve()


settings = Settings()
DATA_DIR = settings.data_path
UPLOADS_DIR = DATA_DIR / 'uploads'
SITE_FILE = DATA_DIR / 'site.json'
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
