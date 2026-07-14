"""Identificación opcional de usuario para services/extraccion/ — services/extraccion/auth.py

A diferencia de presupuestacion/, este servicio no tiene roles ni RLS propios, y hoy
conviven dos consumidores del mismo endpoint /procesar: el HTML viejo (sin ningún
concepto de sesión — corre en un servidor interno sin exposición a internet, y hoy
nadie tiene cuenta en Supabase Auth) y el frontend nuevo (con login real). Por eso la
identificación acá es OPCIONAL, no un gate que bloquea: si viene un JWT válido se usa
para atribución real (processing_sessions.subido_por); si no viene ninguno, la request
sigue funcionando exactamente igual que antes (subido_por=NULL). Pasa a ser obligatoria
recién cuando se retire el HTML viejo — ver ROADMAP.md de presupuestacion/.
"""
import logging
import os

from fastapi import Depends, Header, HTTPException

from services.extraccion.supabase_client import get_client
from services.shared.auth_jwt import TokenInvalidoError, verificar_token

logger = logging.getLogger(__name__)


def get_bearer_token_opcional(authorization: str | None = Header(None)) -> str | None:
    """None si no hay header (caller anónimo, ej. el HTML viejo). 401 si el header
    está pero está malformado -- si alguien manda un Authorization, tiene que tener
    la forma correcta; no se degrada en silencio a "sin auth"."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401, detail="El header Authorization debe ser 'Bearer <token>'"
        )
    return token


def get_usuario_id_actual(token: str | None = Depends(get_bearer_token_opcional)) -> str | None:
    """Devuelve el usuario_id (claim 'sub') si se pudo identificar de forma real, o
    None si la request es anónima o el token es válido pero no tiene perfil en
    usuarios todavía. Levanta 401 si se mandó un token pero es inválido o está
    vencido -- eso sí es un error real del caller, no un caso anónimo."""
    if token is None:
        return None

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    if not supabase_url:
        raise HTTPException(status_code=503, detail="Autenticación no configurada (falta SUPABASE_URL)")

    try:
        payload = verificar_token(token, supabase_url=supabase_url)
    except TokenInvalidoError as exc:
        raise HTTPException(status_code=401, detail="Token inválido o vencido") from exc

    usuario_id = payload["sub"]

    client = get_client()
    if client is not None:
        resultado = client.table("usuarios").select("id").eq("id", usuario_id).limit(1).execute()
        if not resultado.data:
            logger.warning(
                "get_usuario_id_actual: token válido pero sub=%s no tiene fila en "
                "usuarios — se continúa sin atribución.",
                usuario_id,
            )
            return None

    return usuario_id
