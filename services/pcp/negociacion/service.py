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

from services.pcp.documentos.port import PdfRenderer
from services.pcp.documentos.renderer_reportlab import ReportlabPdfRenderer
from services.pcp.gestion import service as gestion_service
from services.pcp.historial import service as historial_service
from services.pcp.mensajeria.adapters import get_mensajeria
from services.pcp.mensajeria.port import MensajeAdjunto, MensajeriaPort
from services.pcp.negociacion import repository as repo
from services.pcp.negociacion.models import RegistrarResultadoNegociacion
from services.pcp.renglones import service as renglones_service
from services.presupuestacion.notificaciones.service import crear_notificacion
from services.presupuestacion.pricing.service import generar_presupuesto_para_endpoint
from services.productos import service as productos_service
from services.shared.config import get_settings
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


# -- 11.7-11.11 (tasks.md Fase 11, design.md D10): cierre de PCP + feedback
# loop Comercial --------------------------------------------------------------
#
# design.md coloca `cerrar_pcp` acá (negociacion/service.py) aunque cerrar un
# PCP es, en esencia, una transición de estado (`pcp.estado` -> `'cerrada'`),
# dominio natural de `gestion/service.py::cambiar_estado` (que ya tiene el
# mapa completo de transiciones, incluida `esperando_respuesta` -> `cerrada`,
# y ya escribe el evento `estado_cambiado`). Esa decisión de diseño ya está
# tomada; acá se sigue tal cual (D10), pero `cerrar_pcp` es un ORCHESTRATOR:
# delega la transición real en `gestion_service.cambiar_estado` (reusa toda
# la validación existente, nunca la reimplementa ni la bypasea) y encima
# ejecuta los efectos de PR11 (PDF + email siempre; notificación interna +
# repricing automático solo si PCP_REPRICING_AUTOMATICO está prendido).
#
# Fase A (siempre activa, D10 "now"): renderiza el PDF de resultado y llama
# `get_mensajeria().enviar_email(...)` a `usuarios.email` de
# `pcp.solicitante_id` -- con el adaptador default (`log`) esto es un no-op
# registrado (D9), así que el módulo funciona sin ningún vendor configurado.
#
# Fase B (`PCP_REPRICING_AUTOMATICO`, default apagado, D10 "later"): agrega
# una notificación interna (`TipoNotificacion.pcp_cerrada`) y dispara
# repricing automático vía el seam público
# `pricing.service.generar_presupuesto_para_endpoint` -- solo si el
# presupuesto de origen sigue `generado`/`en_revision`. Guardada dos veces
# (config flag + esa precondición, D10) -- nunca después de
# `aprobado`/`presentado`.


def _armar_datos_resultado_pdf(
    client: Client, *, pcp: dict[str, Any], drogueria_id: str
) -> dict[str, Any]:
    """Arma la estructura de datos que consume
    `PdfRenderer.render_resultado_pcp` (D10): el PCP entero, con TODOS los
    resultados de negociación por proveedor de cada renglón -- no solo el
    ganador -- para que el solicitante vea el panorama completo."""
    renglones_pcp = renglones_service.listar_renglones(
        client, pcp_id=pcp["id"], drogueria_id=drogueria_id
    )
    renglones: list[dict[str, Any]] = []
    for renglon in renglones_pcp:
        producto = None
        if renglon.get("producto_id"):
            producto = productos_service.obtener_producto(
                client, producto_id=renglon["producto_id"], drogueria_id=drogueria_id
            )
        resultados = renglones_service.listar_resultados_renglon(
            client, renglon_id=renglon["id"], drogueria_id=drogueria_id
        )
        renglones.append({"renglon": renglon, "producto": producto, "resultados": resultados})
    return {"pcp": pcp, "renglones": renglones}


def _notificar_y_repricing_si_corresponde(
    client: Client, *, pcp: dict[str, Any], usuario_id: str
) -> None:
    if not get_settings().pcp_repricing_automatico:
        return

    if pcp.get("solicitante_id") is not None:
        crear_notificacion(
            client,
            drogueria_id=pcp["drogueria_id"],
            destinatario_id=pcp["solicitante_id"],
            tipo="pcp_cerrada",
            titulo="PCP cerrado",
            mensaje=f"El PCP '{pcp['id']}' fue cerrado y está listo para revisión.",
            origen="sistema",
        )

    presupuesto = repo.buscar_estado_presupuesto(client, presupuesto_id=pcp["presupuesto_id"])
    presupuesto_sigue_abierto = presupuesto is not None and presupuesto["estado"] in (
        "generado",
        "en_revision",
    )
    if presupuesto_sigue_abierto:
        generar_presupuesto_para_endpoint(
            proceso_comercial_id=pcp["proceso_comercial_id"],
            drogueria_id=pcp["drogueria_id"],
            disparado_por=usuario_id,
        )


def cerrar_pcp(
    client: Client,
    *,
    pcp_id: str,
    drogueria_id: str,
    usuario_id: str,
    es_superadmin: bool = False,
    renderer: PdfRenderer | None = None,
    mensajeria: MensajeriaPort | None = None,
) -> dict[str, Any]:
    """11.7: cierra un PCP (delegando la transición real en
    `gestion_service.cambiar_estado`, D10) y ejecuta el feedback loop
    Comercial completo -- Fase A siempre, Fase B solo si
    `PCP_REPRICING_AUTOMATICO` está prendido."""
    pcp = gestion_service.cambiar_estado(
        client,
        pcp_id=pcp_id,
        drogueria_id=drogueria_id,
        estado_nuevo="cerrada",
        usuario_id=usuario_id,
        es_superadmin=es_superadmin,
    )

    if pcp.get("solicitante_id") is None:
        raise ValidationError(
            "El PCP no tiene un solicitante asociado; no se puede notificar el cierre"
        )
    email_solicitante = repo.obtener_email_usuario(client, usuario_id=pcp["solicitante_id"])
    if email_solicitante is None:
        raise ValidationError(
            f"No se pudo resolver el email del usuario solicitante '{pcp['solicitante_id']}'"
        )

    datos_pdf = _armar_datos_resultado_pdf(client, pcp=pcp, drogueria_id=drogueria_id)
    renderer = renderer or ReportlabPdfRenderer()
    pdf_bytes = renderer.render_resultado_pcp(datos_pdf)

    mensajeria = mensajeria or get_mensajeria()
    resultado_envio = mensajeria.enviar_email(
        destinatario=email_solicitante,
        asunto=f"Resultado del PCP '{pcp_id}'",
        cuerpo="El pedido de cotización de precios que solicitaste fue cerrado. Se adjunta el resultado.",
        adjuntos=[MensajeAdjunto(nombre=f"pcp-{pcp_id}-resultado.pdf", contenido=pdf_bytes)],
    )

    # D6: nunca un campo de costo/precio crudo en el payload -- solo el
    # resultado del envío (mismo criterio que `registrar_resultado`).
    historial_service.agregar_evento(
        client,
        drogueria_id=drogueria_id,
        pcp_id=pcp_id,
        tipo_evento="notificacion_enviada",
        payload={
            "canal": "email",
            "entregado": resultado_envio.entregado,
            "proveedor_externo": resultado_envio.proveedor_externo,
        },
        usuario_id=usuario_id,
    )

    _notificar_y_repricing_si_corresponde(client, pcp=pcp, usuario_id=usuario_id)

    return pcp


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


def cerrar_pcp_para_endpoint(
    *, pcp_id: str, drogueria_id: str, usuario_id: str, es_superadmin: bool = False
) -> dict[str, Any]:
    return cerrar_pcp(
        get_service_client(),
        pcp_id=pcp_id,
        drogueria_id=drogueria_id,
        usuario_id=usuario_id,
        es_superadmin=es_superadmin,
    )
