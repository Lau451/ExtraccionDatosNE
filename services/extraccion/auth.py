"""Autenticación obligatoria para services/extraccion/ — services/extraccion/auth.py

Multi-tenant (2026-09-25): el HTML legacy (histórico único consumidor sin JWT real)
se retira en T2 del cambio `extraccion-multi-tenant`; a partir de acá TODO endpoint
no-legacy exige un JWT real, igual que services/presupuestacion/. Reexporta
UsuarioPerfil/get_current_user de services.shared.auth (mismo mecanismo ya usado por
services/presupuestacion y services/terceros) y agrega get_drogueria_id_actual, que
extrae drogueria_id del perfil autenticado y falla explícito (403) si no está seteado.

Sin fallback silencioso a ninguna droguería por default: cada request obtiene su
drogueria_id del perfil del usuario autenticado, nunca de env ni de un valor por
defecto (ver services/extraccion/supabase_client.py).
"""
from fastapi import Depends, HTTPException, status

from services.shared.auth import (
    UserClaims,
    UsuarioPerfil,
    get_current_claims,
    get_current_user,
    require_roles,
)

__all__ = [
    "ROLES_EXTRACCION",
    "UserClaims",
    "UsuarioPerfil",
    "get_current_claims",
    "get_current_user",
    "get_drogueria_id_actual",
]

# Roles con acceso a la carga y extracción de documentos (odd/tasks/
# roles-permisos-matriz.md S1): compras y superadmin no participan por ahora.
ROLES_EXTRACCION = ("admin", "gerencia", "lider_comercial", "comercial")


def get_drogueria_id_actual(
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_EXTRACCION)),
) -> str:
    """Droguería del usuario autenticado, para enhebrar explícitamente en cada función
    de persistencia/consulta de services/extraccion/ (crear_sesion, guardar_chunk,
    persistir_output_final, buscar_duplicado_con_lock, procesos_comerciales_client,
    routers/clientes.py). Como todo endpoint del servicio depende de esta
    función, también es el guard de rol: 403 si el rol no está en
    ROLES_EXTRACCION.

    403 si el perfil no tiene una droguería asignada (p.ej. un superadmin futuro) --
    este servicio no tiene concepto de "todas las droguerías", a diferencia de
    services/presupuestacion/ (RLS + superadmin exento)."""
    if not usuario.drogueria_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no tiene una droguería asignada",
        )
    return usuario.drogueria_id
