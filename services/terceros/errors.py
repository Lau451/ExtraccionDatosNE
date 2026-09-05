"""Guard único D3 (openspec/changes/terceros-modelo/design.md): un solo patrón
de error para todo services/terceros/, sin excepciones por submódulo.

    | Situación                                                       | Excepción      |
    |------------------------------------------------------------------|----------------|
    | La fila no existe o pertenece a otra droguería (no superadmin)   | NotFoundError  |
    | Rol insuficiente dentro de la misma droguería                    | ForbiddenError |
    | Input malformado o regla de negocio violada                      | ValidationError|
    | Violación de unicidad (código o nombre repetido)                 | ConflictError  |

`asegurar_tercero_de_la_drogueria` cubre la primera fila: se invoca una sola
vez, solo en la capa de servicio (nunca en el router), y nunca distingue
"no existe" de "es de otra droguería" -- ambos casos son indistinguibles
desde afuera, así que ambos devuelven NotFoundError. Los routers de
services/terceros/ no revalidan pertenencia por su cuenta.
"""

from typing import Any

from services.shared.exceptions import NotFoundError

# Código Postgres de unique_violation (usado por las capas de servicio de
# este módulo para traducir un APIError de postgrest a ConflictError).
UNIQUE_VIOLATION = "23505"


def asegurar_tercero_de_la_drogueria(
    fila: dict[str, Any] | None,
    *,
    drogueria_id: str,
    es_superadmin: bool = False,
    entidad: str = "el recurso",
) -> dict[str, Any]:
    if fila is None:
        raise NotFoundError(f"No se encontró {entidad}")
    if fila["drogueria_id"] != drogueria_id and not es_superadmin:
        raise NotFoundError(f"No se encontró {entidad}")
    return fila
