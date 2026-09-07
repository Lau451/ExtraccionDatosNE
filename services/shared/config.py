from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    usuario_sistema_id: str
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    frontend_url: str = "http://localhost:5173"

    # gestor-pcp PR11 (design.md D9/D10) -- feature flags del módulo
    # services/pcp/. `pcp_mensajeria_adapter` selecciona el adaptador de
    # `services/pcp/mensajeria/adapters.py::get_mensajeria()` ("log" es el
    # único implementado en este PR; ningún vendor default, D9).
    # `pcp_repricing_automatico` (default apagado) guarda todo el "Comercial
    # Feedback Loop -- Internal Notification and Auto-Repricing Phase"
    # (D10/spec pcp-sugerencias): mientras esté en False, cerrar un PCP nunca
    # crea una notificación interna ni dispara repricing automático -- solo
    # el email de resultado (Phase A, siempre activo).
    pcp_mensajeria_adapter: str = "log"
    pcp_repricing_automatico: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
