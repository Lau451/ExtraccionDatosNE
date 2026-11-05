from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
_INTERVALO_ESCANEO_DEFAULT = 300


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    usuario_sistema_id: str
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
    # login-usuario-alta-admin S2: dominio de los emails internos y opacos
    # (`<uuid>@<dominio>`) con los que se crean las cuentas de Supabase Auth. Nunca
    # se envía correo a esas direcciones ni se muestran en el frontend.
    auth_email_domain: str = "usuarios.local"

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

    # oc-export-progress (design.md D8): carpeta donde se deposita el CSV de la OC
    # para Progress. None => la exportación responde 503 (IntegracionNoConfigurada).
    progress_docs_dir: str | None = None
    oc_export_encoding: str = "cp1252"

    # integracion-progress S4/L6: recepción automática desde la carpeta de entrada.
    # Los archivos de tipo `presupuestos` se leen de <progress_entrada_dir>/presupuestos
    # y se importan en el tenant `progress_drogueria_id` con el usuario de sistema.
    # Sin carpeta o sin tenant la recepción automática queda apagada; un string
    # vacío del entorno cuenta como no configurado.
    progress_entrada_dir: str | None = None
    progress_drogueria_id: str | None = None
    progress_escaneo_intervalo_segundos: int = Field(default=_INTERVALO_ESCANEO_DEFAULT, ge=1)

    @field_validator("progress_entrada_dir", "progress_drogueria_id", mode="before")
    @classmethod
    def _vacio_es_no_configurado(cls, valor: object) -> object:
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @field_validator("progress_escaneo_intervalo_segundos", mode="before")
    @classmethod
    def _intervalo_vacio_es_default(cls, valor: object) -> object:
        if isinstance(valor, str) and not valor.strip():
            return _INTERVALO_ESCANEO_DEFAULT
        return valor

    @property
    def cors_origins_list(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
