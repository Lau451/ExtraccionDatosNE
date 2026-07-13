"""
Supabase client singleton con feature flag: app/supabase_client.py

Provee una única instancia compartida del cliente Supabase para todo el proceso.
Si ENABLE_RESULT_PERSISTENCE=false o las variables de entorno están ausentes,
todas las funciones de persistencia se comportan como no-ops (retornan None/False).

Variables de entorno requeridas:
  SUPABASE_URL             — URL del proyecto (ej: https://xyz.supabase.co)
  SUPABASE_SERVICE_KEY     — Service role key (nunca anon; necesita bypassear RLS)
  ENABLE_RESULT_PERSISTENCE — "true" / "false" (default: "true")
"""

import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intento de importar supabase-py; si no está instalado la persistencia
# queda deshabilitada silenciosamente (no rompe el arranque del servidor).
# ---------------------------------------------------------------------------
try:
    from supabase import create_client, Client  # type: ignore
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    Client = None  # type: ignore

# ---------------------------------------------------------------------------
# Singleton interno — se inicializa en el primer get_client()
# ---------------------------------------------------------------------------
_client: "Client | None" = None  # type: ignore

# Cache en proceso del id de la (unica) drogueria — esta app hoy sirve una sola.
# Si en el futuro sirve mas de una, esto necesita resolverse por request, no aca.
_drogueria_id_cache: "str | None" = None


def _persistence_enabled() -> bool:
    """Verifica si el feature flag ENABLE_RESULT_PERSISTENCE está activo."""
    return os.getenv("ENABLE_RESULT_PERSISTENCE", "true").lower() == "true"


def get_client() -> "Client | None":  # type: ignore
    """
    Retorna el cliente Supabase compartido.

    Retorna None si:
      - ENABLE_RESULT_PERSISTENCE=false
      - supabase-py no está instalado
      - SUPABASE_URL o SUPABASE_SERVICE_KEY no están configuradas

    Dos llamadas consecutivas retornan el MISMO objeto (singleton).
    Thread-safe: supabase-py reutiliza un pool HTTP interno.
    """
    global _client

    if not _persistence_enabled():
        return None

    if not _SUPABASE_AVAILABLE:
        logger.warning(
            "supabase-py no está instalado — persistencia deshabilitada. "
            "Instalá con: pip install supabase"
        )
        return None

    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = (
        os.getenv("SUPABASE_SERVICE_KEY", "")
        or os.getenv("SUPABASE_KEY", "")
    ).strip()

    if not url or not key:
        logger.warning(
            "Supabase no configurado (SUPABASE_URL / SUPABASE_SERVICE_KEY ausentes) "
            "— persistencia deshabilitada"
        )
        return None

    try:
        _client = create_client(url, key)
        logger.info("Cliente Supabase inicializado correctamente")
    except Exception as exc:
        logger.error("Error al inicializar cliente Supabase: %s", exc)
        return None

    return _client


def is_enabled() -> bool:
    """
    Retorna True si la persistencia está activa y el cliente disponible.
    Útil para guardia rápida: `if not is_enabled(): return None`.
    """
    return get_client() is not None


def resolver_drogueria_id_unica(client: "Client") -> "str | None":
    """
    Resuelve el id de la (unica) drogueria que sirve esta app — cacheado en
    proceso. Usado por todo el codigo que persiste en el schema nuevo de
    presupuestacion/ (extraction_results, processing_sessions, chunk_results),
    donde drogueria_id es NOT NULL pero esta app no tiene ese concepto en su
    propio dominio.

    Retorna None si la consulta falla (el llamador decide si eso es fatal).
    """
    global _drogueria_id_cache
    if _drogueria_id_cache is not None:
        return _drogueria_id_cache

    try:
        respuesta = client.table("droguerias").select("id").limit(1).execute()
        if respuesta.data:
            _drogueria_id_cache = respuesta.data[0]["id"]
            return _drogueria_id_cache
    except Exception as exc:
        logger.error("resolver_drogueria_id_unica: error consultando droguerias — %s", exc)

    return None


def reset_client_for_testing() -> None:
    """
    Resetea el singleton (y el cache de drogueria_id). SOLO para usar en tests
    con mocks de entorno. No llamar en código de producción.
    """
    global _client, _drogueria_id_cache
    _client = None
    _drogueria_id_cache = None
