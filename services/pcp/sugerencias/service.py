"""Servicio de sugerencias de PCP (design.md D12, spec `pcp-sugerencias`).

D12: "las sugerencias son consultas, no tablas" -- ninguna función de este
módulo escribe nada; ambas son lecturas puras sobre `pcp`/`pcp_renglones` y
la vista `v_precios_especiales_vigentes` (0012_pcp_extras.sql M6, vigente
desde PR2). Ignorar una sugerencia nunca fusiona ni modifica un PCP (spec
"Suggestion Never Auto-merges PCPs") porque no existe ningún code path de
escritura que llamar -- una heurística equivocada es, por diseño, un cambio
de consulta, nunca una migración (D12).

Solo cubre las dos sugerencias de v1 confirmadas por el diseño (agrupación
por cantidad, reuso de precio reciente). El feedback loop hacia Comercial
(email al cerrar el PCP / notificación interna + auto-repricing) es una fase
separada (PR11): depende de `MensajeriaPort`
(`services/pcp/mensajeria/`), que este PR no toca ni referencia.

Ambas funciones se anclan en un `renglon_id`, no en un `producto_id` suelto
-- mismo criterio que "cuando se abre un renglón de PCP para ese artículo"
en la spec, y el mismo patrón ya usado por
`services/pcp/renglones/service.py::listar_proveedores_disponibles_renglon`
(resolver el producto del renglón primero, después consultar sobre ese
producto).
"""

from decimal import Decimal
from typing import Any

from supabase import Client

from services.pcp.renglones import service as renglones_service
from services.pcp.sugerencias import repository as repo

# D12 no fija un número concreto de días para "PCPs cercanos a su fecha de
# entrega solicitada". D7 (reglas_pcp) es un seam sin motor todavía en este
# PR, así que no hay ninguna regla/config que lo parametrice -- un default a
# nivel de módulo, overridable por el caller (query param del router), evita
# hardcodear el número sin posibilidad de ajuste futuro sin tocar código.
DIAS_VENTANA_AGRUPACION_DEFAULT = 15


def sugerir_agrupacion_por_renglon(
    client: Client,
    *,
    renglon_id: str,
    drogueria_id: str,
    dias: int = DIAS_VENTANA_AGRUPACION_DEFAULT,
) -> dict[str, Any] | None:
    """Spec "Quantity-Grouping Suggestion". Devuelve `None` cuando:
    - el renglón todavía no tiene producto matcheado (nada que agrupar por);
    - el propio PCP del renglón no está "por vencer" dentro de la ventana de
      `dias` (D12) -- sin esa condición, no hay base para sugerirle nada al
      usuario que está viendo justamente este renglón;
    - es el único PCP abierto y por vencer para ese producto (D12 exige "más
      de un pcp_id distinto").

    Nunca escribe: la sugerencia se recalcula en cada llamada, así que
    ignorarla dos veces produce el mismo resultado sin ningún efecto
    colateral sobre `pcp`/`pcp_renglones` (spec "Suggestion Never
    Auto-merges PCPs")."""
    renglon = renglones_service.obtener_renglon(client, renglon_id=renglon_id, drogueria_id=drogueria_id)
    producto_id = renglon.get("producto_id")
    if producto_id is None:
        return None

    pcps_por_vencer = repo.listar_pcp_abiertos_por_vencer(client, drogueria_id=drogueria_id, dias=dias)
    pcp_ids_por_vencer = [fila["id"] for fila in pcps_por_vencer]
    if renglon["pcp_id"] not in pcp_ids_por_vencer:
        return None

    renglones = repo.listar_renglones_por_producto_en_pcps(
        client, drogueria_id=drogueria_id, producto_id=producto_id, pcp_ids=pcp_ids_por_vencer
    )
    pcp_ids_involucrados = sorted({fila["pcp_id"] for fila in renglones})
    if len(pcp_ids_involucrados) < 2:
        return None

    cantidad_agregada = sum(
        (Decimal(str(fila["cantidad"])) for fila in renglones if fila.get("cantidad") is not None),
        Decimal("0"),
    )
    return {
        "producto_id": producto_id,
        "cantidad_agregada": cantidad_agregada,
        "pcp_ids": pcp_ids_involucrados,
        "renglon_ids": [fila["id"] for fila in renglones],
    }


def sugerir_precios_recientes_por_renglon(
    client: Client, *, renglon_id: str, drogueria_id: str
) -> list[dict[str, Any]]:
    """Spec "Recent-Price-Reuse Suggestion". `[]` cuando el renglón todavía
    no tiene producto matcheado -- sin producto no hay nada que buscar en
    `v_precios_especiales_vigentes`."""
    renglon = renglones_service.obtener_renglon(client, renglon_id=renglon_id, drogueria_id=drogueria_id)
    producto_id = renglon.get("producto_id")
    if producto_id is None:
        return []
    return repo.listar_precios_especiales_vigentes_por_producto(
        client, drogueria_id=drogueria_id, producto_id=producto_id
    )
