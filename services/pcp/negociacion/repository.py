from typing import Any

from supabase import Client


def crear_precio_proveedor(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    """Escribe una fila en `precios_proveedor` (D4/D5) -- el primer escritor
    real de esta tabla (`services/presupuestacion/pricing/repository.py` solo
    la lee). `item_proceso_id` siempre viene seteado por el caller (D4:
    "precio puntual", nunca un precio general de producto)."""
    return client.table("precios_proveedor").insert(fila).execute().data[0]


def obtener_precio_proveedor(client: Client, *, precio_proveedor_id: str) -> dict[str, Any] | None:
    """Lectura del JOIN que alimenta `ResultadoNegociacionOut` (design.md
    "Comparison Table"): `pcp_renglon_resultados` solo guarda
    `precio_proveedor_id`, los valores de precio/condiciones viven en
    `precios_proveedor` (`crear_precio_proveedor` es quien la escribe)."""
    resultado = (
        client.table("precios_proveedor")
        .select("*")
        .eq("id", precio_proveedor_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_resultado(
    client: Client, *, pcp_renglon_id: str, proveedor_id: str
) -> dict[str, Any] | None:
    """`select` embebe `precios_proveedor` vía la FK `fk_ppr_precio_prov` en
    la misma consulta -- un solo round trip en vez de dos (la fila más, si
    corresponde, su precio/condiciones), sin depender de un segundo lookup
    por `precio_proveedor_id`."""
    resultado = (
        client.table("pcp_renglon_resultados")
        .select("*, precios_proveedor(*)")
        .eq("pcp_renglon_id", pcp_renglon_id)
        .eq("proveedor_id", proveedor_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def obtener_email_usuario(client: Client, *, usuario_id: str) -> str | None:
    """PR11 (tasks.md 11.7) -- `usuarios` (rls_final.sql) NO tiene columna
    `email`: vive en `auth.users`, accesible únicamente vía la Admin API de
    Supabase Auth (`client.auth.admin.get_user_by_id`, mismo mecanismo que
    `services/presupuestacion/usuarios/repository.py::invitar_usuario_auth`
    usa para crear el usuario). Requiere que `client` esté inicializado con
    la service_role key -- `cerrar_pcp` solo se expone vía su wrapper
    `*_para_endpoint` (service_role), igual que el resto de operaciones de
    escritura cross-tabla de este módulo. Devuelve `None` si el usuario no
    existe en Auth (nunca levanta: el caller decide qué error de dominio
    corresponde)."""
    try:
        respuesta = client.auth.admin.get_user_by_id(usuario_id)
    except Exception:
        return None
    return respuesta.user.email if respuesta and respuesta.user else None


def buscar_estado_presupuesto(client: Client, *, presupuesto_id: str) -> dict[str, Any] | None:
    """Lectura directa de `presupuestos.estado` -- mismo criterio que
    `services/pcp/gestion/repository.py::buscar_presupuesto` (D1: el acceso a
    la tabla en sí, fuera de un import Python de otro `repository`, no está
    restringido por ese guard). Copia local intencional en vez de reusar
    `gestion.repository` (D1 no lo prohíbe, pero cada submódulo de PCP ya
    sigue este mismo patrón -- ver docstring de
    `gestion/service.py::_UNIQUE_VIOLATION`)."""
    resultado = (
        client.table("presupuestos")
        .select("id, estado")
        .eq("id", presupuesto_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def upsert_resultado(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    """Upsert por `uq_ppr_renglon_prov (pcp_renglon_id, proveedor_id)`
    (0011_pcp_modelo.sql M4): actualiza la fila que
    `services/pcp/renglones/service.py::seleccionar_proveedores` (PR5) dejó
    en `resultado='sin_respuesta'` sin crear una segunda fila (la UNIQUE lo
    impediría igual, pero un INSERT crudo fallaría con `23505` en vez de
    transicionar la fila existente). Si por algún motivo no existía una
    selección previa para ese par renglón-proveedor, el mismo upsert la crea
    -- ninguna consulta previa es necesaria."""
    return (
        client.table("pcp_renglon_resultados")
        .upsert(fila, on_conflict="pcp_renglon_id,proveedor_id")
        .execute()
        .data[0]
    )


def actualizar_seleccion(
    client: Client, *, pcp_renglon_id: str, proveedor_id: str, seleccionado: bool
) -> dict[str, Any] | None:
    resultado = (
        client.table("pcp_renglon_resultados")
        .update({"seleccionado": seleccionado})
        .eq("pcp_renglon_id", pcp_renglon_id)
        .eq("proveedor_id", proveedor_id)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_resultados_renglon(client: Client, *, pcp_renglon_id: str) -> list[dict[str, Any]]:
    """Lectura batched -- un único round trip para todos los proveedores de
    un renglón (con `precios_proveedor` embebido, misma FK que
    `buscar_resultado`), en vez del fan-out de N llamados que el frontend
    hacía antes (uno por proveedor vía `obtener_resultado`)."""
    return (
        client.table("pcp_renglon_resultados")
        .select("*, precios_proveedor(*)")
        .eq("pcp_renglon_id", pcp_renglon_id)
        .execute()
        .data
    )


def listar_pcp_renglon_proveedor_seleccionados(
    client: Client, *, pcp_renglon_ids: list[str]
) -> list[dict[str, Any]]:
    """Devuelve el par `(pcp_renglon_id, proveedor_id)` completo para cada
    selección persistida. Alimenta `agrupar_renglones` (`consultas/service.py`)
    y, deduplicado por renglón, el badge "Negociado" de Gestión vía
    `service.py::listar_renglones_seleccionados` (Corrective Rerun --
    Consultas grouping scope, apply-progress.md): un renglón puede tener más
    de un proveedor `seleccionado` (Work Unit 5), así que las filas no se
    deduplican por renglón acá -- solo el caller que arma el badge lo hace."""
    if not pcp_renglon_ids:
        return []
    return (
        client.table("pcp_renglon_resultados")
        .select("pcp_renglon_id, proveedor_id")
        .in_("pcp_renglon_id", pcp_renglon_ids)
        .eq("seleccionado", True)
        .execute()
        .data
    )
