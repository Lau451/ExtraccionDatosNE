"""Destino del archivo de presupuestos: la fachada de PCP, dueña de
`presupuesto_legacy_map` y de la idempotencia del import (S5). Este módulo no
escribe tablas ajenas: valida las filas contra el modelo del dueño y se las entrega."""

from typing import Any

from supabase import Client

from services.pcp.api import FilaImportPresupuestoLegacy, importar_presupuesto_legacy


def entregar(
    client: Client, *, drogueria_id: str, filas: list[dict[str, Any]], usuario_id: str
) -> list[dict[str, Any]]:
    """Entrega las filas parseadas a `services.pcp.api.importar_presupuesto_legacy`.
    Devuelve un resultado por `numero_presupuesto` (ImportPresupuestoLegacyResultado)."""
    return importar_presupuesto_legacy(
        client,
        drogueria_id=drogueria_id,
        filas=[FilaImportPresupuestoLegacy.model_validate(fila) for fila in filas],
        usuario_id=usuario_id,
    )
