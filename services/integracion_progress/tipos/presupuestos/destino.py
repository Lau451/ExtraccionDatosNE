"""Destino del archivo de presupuestos: la fachada de `comercial`
(`services.presupuestacion.presupuestos.api`), dueña de `presupuesto_legacy_map`
y de la idempotencia del import (S5; odd/tasks/procesos-comerciales-dueno.md S1).
Este módulo no escribe tablas ajenas: valida las filas contra el modelo del dueño y
se las entrega."""

from typing import Any

import pydantic
from supabase import Client

from services.presupuestacion.presupuestos.api import (
    FilaImportPresupuestoLegacy,
    importar_presupuesto_legacy,
)
from services.shared.exceptions import ValidationError


def _validar(filas: list[dict[str, Any]]) -> list[FilaImportPresupuestoLegacy]:
    """Filas del parser → modelo del dueño. Si el parser y el modelo del dueño dejan de
    coincidir, es un error de validación del archivo (no un error inesperado) y no se
    entrega ninguna fila."""
    validadas: list[FilaImportPresupuestoLegacy] = []
    for numero, fila in enumerate(filas, start=1):
        try:
            validadas.append(FilaImportPresupuestoLegacy.model_validate(fila))
        except pydantic.ValidationError as exc:
            campos = ", ".join(
                sorted({".".join(str(parte) for parte in e["loc"]) for e in exc.errors()})
            )
            raise ValidationError(
                f"La fila {numero} no tiene el formato que espera PCP (campo {campos})"
            ) from None
    return validadas


def entregar(
    client: Client, *, drogueria_id: str, filas: list[dict[str, Any]], usuario_id: str
) -> list[dict[str, Any]]:
    """Entrega las filas parseadas a
    `services.presupuestacion.presupuestos.api.importar_presupuesto_legacy`.
    Devuelve un resultado por `numero_presupuesto` (ImportPresupuestoLegacyResultado)."""
    return importar_presupuesto_legacy(
        client,
        drogueria_id=drogueria_id,
        filas=_validar(filas),
        usuario_id=usuario_id,
    )
