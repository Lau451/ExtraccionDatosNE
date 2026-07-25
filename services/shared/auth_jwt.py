"""Verificación de JWT de Supabase Auth, compartida entre services/extraccion/ y
services/presupuestacion/ -- sin lógica de negocio de ningún dominio: solo valida la
firma/vigencia del token contra el JWKS de Supabase y devuelve las claims crudas. Cada
servicio decide qué hacer con ellas (resolver rol, droguería, exigir un usuario_id para
atribución, etc.) del lado de su propio módulo de auth."""
from functools import lru_cache

import jwt
from jwt import PyJWKClient


class TokenInvalidoError(Exception):
    """El token no pudo verificarse: firma inválida, vencido o malformado."""


@lru_cache
def _jwk_client(supabase_url: str) -> PyJWKClient:
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url)


def verificar_token(token: str, *, supabase_url: str) -> dict:
    """Verifica firma y vigencia contra el JWKS de Supabase. Devuelve el payload
    crudo (dict, incluye al menos 'sub' y 'exp') si es válido; levanta
    TokenInvalidoError si no."""
    try:
        signing_key = _jwk_client(supabase_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "HS256"],
            audience="authenticated",
            # Tolera pequeños desfasajes de reloj entre esta máquina y el servidor de
            # Supabase que emitió el token -- sin esto, `iat` puede caer segundos en
            # el "futuro" y jwt.decode lo rechaza con ImmatureSignatureError incluso
            # con un token recién emitido y válido (reproducido: ~2s de desfasaje
            # bastaban para tumbar el login de forma intermitente).
            leeway=10,
        )
    except jwt.PyJWTError as exc:
        raise TokenInvalidoError("Token inválido o vencido") from exc
