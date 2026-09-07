"""Servicio de negociación de PCP (0011_pcp_modelo.sql M4, 0012_pcp_extras.sql
M5, design.md D4/D5, spec `pcp-negociacion`).

`precios_proveedor` sigue siendo el registro de precio (D4): este módulo es
su primer escritor real, y solo escribe una fila cuando el resultado es
`precio_obtenido` -- `no_cotiza` nunca fabrica una fila de precio, solo
transiciona el `pcp_renglon_resultados` que PR5 dejó en `sin_respuesta`.

Ventana de vigencia (spec "Validity Window via mantenimiento_hasta", tasks.md
7.6): puramente una preocupación de LECTURA, ya resuelta por
`pricing/repository.py::buscar_precio_especial_puntual` (filtra
`mantenimiento_hasta >= hoy`), sin cambios en este PR. Del lado de la
escritura, `ck_pp_mant CHECK (mantenimiento_hasta >= fecha_oferta)`
(docs/schema/extractor_final.sql) ya impide, a nivel de base, registrar un
precio nacido vencido en el flujo normal: `fecha_oferta` no se expone en
`RegistrarResultadoNegociacion` (usa el `DEFAULT CURRENT_DATE` de la
columna), así que un `mantenimiento_hasta` en el pasado nunca pasa el CHECK
al registrar hoy. No hace falta duplicar esa regla en Python.
"""

from typing import Any

from supabase import Client

from services.pcp.historial import service as historial_service
from services.pcp.negociacion import repository as repo
from services.pcp.negociacion.models import RegistrarResultadoNegociacion
from services.pcp.renglones import service as renglones_service
from services.shared.database import get_service_client
from services.shared.exceptions import NotFoundError, ValidationError
from services.terceros.api import obtener_condicion_pago, obtener_forma_pago


def _validar_condicion_y_forma_pago(
    client: Client, *, drogueria_id: str, condicion_pago_id: str | None, forma_pago_id: str | None
) -> None:
    """Mismo criterio que
    `services/terceros/identidad/service.py::_validar_condicion_y_forma_pago`
    (condición/forma deben resolver a filas reales del mismo tenant) --
    copia local, no un import directo: D1 solo permite importar
    `services.terceros.api` (fachada pública), nunca un `service`/`repository`
    interno de otro módulo. Import directo de las funciones (no del módulo
    `services.terceros.api` como alias) -- mismo motivo documentado en
    `services/pcp/catalogo/service.py::agregar_proveedor`:
    `tests/pcp/test_dependencias.py` matchea el `ast.ImportFrom.module` exacto
    contra `services.terceros.api`, y `from services.terceros import api`
    registra el módulo como `services.terceros` (sin el `.api`), que el guard
    no reconoce. `obtener_condicion_pago`/`obtener_forma_pago` ya hacen la
    validación de tenant (levantan `NotFoundError` vía
    `asegurar_tercero_de_la_drogueria`); acá se traduce a `ValidationError`
    para conservar la misma semántica que el original (un id que no
    pertenece a la droguería es un error de validación de la request, no un
    404 de recurso)."""
    if condicion_pago_id is not None:
        try:
            obtener_condicion_pago(
                client, condicion_pago_id=condicion_pago_id, drogueria_id=drogueria_id
            )
        except NotFoundError as exc:
            raise ValidationError(
                "La condición de pago no pertenece a esta droguería"
            ) from exc
    if forma_pago_id is not None:
        try:
            obtener_forma_pago(
                client, forma_pago_id=forma_pago_id, drogueria_id=drogueria_id
            )
        except NotFoundError as exc:
            raise ValidationError("La forma de pago no pertenece a esta droguería") from exc


def registrar_resultado(
    client: Client,
    *,
    drogueria_id: str,
    pcp_renglon_id: str,
    proveedor_id: str,
    body: RegistrarResultadoNegociacion,
    usuario_id: str,
) -> dict[str, Any]:
    # Reusa renglones/service.py::obtener_renglon (submódulo interno de
    # services/pcp/, fuera del alcance del guard D1 -- mismo criterio que
    # renglones reusando gestion/catalogo) para validar tenant/existencia del
    # renglón antes de tocar precios_proveedor o pcp_renglon_resultados.
    renglon = renglones_service.obtener_renglon(
        client, renglon_id=pcp_renglon_id, drogueria_id=drogueria_id
    )

    precio_proveedor_id: str | None = None
    if body.resultado == "precio_obtenido":
        # precios_proveedor.producto_id es NOT NULL (docs/schema/extractor_final.sql):
        # un renglón cuyo matching de producto todavía está pendiente (D2,
        # producto_id nullable) no puede convertirse en un precio puntual.
        if renglon.get("producto_id") is None:
            raise ValidationError(
                "El renglón todavía no tiene un producto matcheado; "
                "no se puede registrar un precio_obtenido"
            )
        _validar_condicion_y_forma_pago(
            client,
            drogueria_id=drogueria_id,
            condicion_pago_id=body.condicion_pago_id,
            forma_pago_id=body.forma_pago_id,
        )

        precio = repo.crear_precio_proveedor(
            client,
            {
                "drogueria_id": drogueria_id,
                "proveedor_id": proveedor_id,
                "producto_id": renglon["producto_id"],
                # D4: precio puntual -- item_proceso_id del renglón, nunca
                # NULL (eso sería un precio general del producto, fuera de
                # alcance de este módulo).
                "item_proceso_id": renglon["item_proceso_id"],
                "precio_unitario": str(body.precio_unitario),
                "cantidad_minima": str(body.cantidad_minima) if body.cantidad_minima is not None else None,
                "cantidad_maxima": str(body.cantidad_maxima) if body.cantidad_maxima is not None else None,
                "mantenimiento_hasta": body.mantenimiento_hasta.isoformat(),
                # D5: condicion_pago_id/forma_pago_id -- nunca plazo_pago_dias
                # (columna deprecada, sin escritura de código nuevo).
                "condicion_pago_id": body.condicion_pago_id,
                "forma_pago_id": body.forma_pago_id,
                "notas": body.notas,
                "creado_por": usuario_id,
            },
        )
        precio_proveedor_id = precio["id"]

    resultado = repo.upsert_resultado(
        client,
        {
            "drogueria_id": drogueria_id,
            "pcp_renglon_id": renglon["id"],
            "proveedor_id": proveedor_id,
            "resultado": body.resultado,
            "precio_proveedor_id": precio_proveedor_id,
            "motivo": body.motivo,
            "registrado_por": usuario_id,
        },
    )

    # D6: todo evento de negociación queda en pcp_historial (append-only) --
    # nunca un campo de costo/precio crudo en el payload, solo el resultado.
    historial_service.agregar_evento(
        client,
        drogueria_id=drogueria_id,
        pcp_id=renglon["pcp_id"],
        pcp_renglon_id=renglon["id"],
        tipo_evento="resultado_registrado",
        payload={"proveedor_id": proveedor_id, "resultado": body.resultado},
        usuario_id=usuario_id,
    )

    return resultado


def obtener_resultado(
    client: Client, *, drogueria_id: str, pcp_renglon_id: str, proveedor_id: str
) -> dict[str, Any]:
    renglon = renglones_service.obtener_renglon(
        client, renglon_id=pcp_renglon_id, drogueria_id=drogueria_id
    )
    resultado = repo.buscar_resultado(client, pcp_renglon_id=renglon["id"], proveedor_id=proveedor_id)
    if resultado is None:
        raise NotFoundError(
            f"No hay un resultado de negociación registrado para el proveedor "
            f"'{proveedor_id}' en el renglón '{pcp_renglon_id}'"
        )
    return resultado


# -- wrappers de endpoint (service_role, mismo criterio que
# services/pcp/renglones/service.py::*_para_endpoint) -----------------------


def registrar_resultado_para_endpoint(
    *,
    drogueria_id: str,
    pcp_renglon_id: str,
    proveedor_id: str,
    body: RegistrarResultadoNegociacion,
    usuario_id: str,
) -> dict[str, Any]:
    return registrar_resultado(
        get_service_client(),
        drogueria_id=drogueria_id,
        pcp_renglon_id=pcp_renglon_id,
        proveedor_id=proveedor_id,
        body=body,
        usuario_id=usuario_id,
    )


def obtener_resultado_para_endpoint(
    *, drogueria_id: str, pcp_renglon_id: str, proveedor_id: str
) -> dict[str, Any]:
    return obtener_resultado(
        get_service_client(),
        drogueria_id=drogueria_id,
        pcp_renglon_id=pcp_renglon_id,
        proveedor_id=proveedor_id,
    )
