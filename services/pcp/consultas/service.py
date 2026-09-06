"""Servicio de consultas agrupadas de PCP (0012_pcp_extras.sql M4, design.md
D9, spec `pcp-consultas-agrupadas`).

Agrupamiento real many-to-many (D9): `pcp_consultas` no tiene `pcp_id`;
`pcp_consulta_renglones` es lo que permite que renglones de PCPs distintos
terminen en una sola consulta a un mismo proveedor. Cada renglón sigue
trazando a su PCP de origen vía `pcp_consulta_renglones.pcp_renglon_id ->
pcp_renglones.pcp_id` -- nunca se copia ni se denormaliza ese dato acá.

"Renglón asignado al proveedor P" (spec "Cross-PCP Grouping by Supplier") se
prueba con la fila `pcp_renglon_resultados` que PR5
(`seleccionar_proveedores`) ya dejó en `sin_respuesta` -- es la única
referencia en todo el esquema entre un renglón y "los proveedores con los
que se lo está negociando" (D4). `agrupar_renglones` reusa
`negociacion_service.obtener_resultado` para esa validación en vez de leer
`pcp_renglon_resultados` directo: mismo criterio que `renglones/service.py`
reusando `gestion_service`/`catalogo_service` -- todos submódulos internos de
`services/pcp/`, fuera del alcance del guard D1.

Decisión de diseño (tasks.md 9.3-9.4, dejada explícitamente a este run por
el launch prompt): un único `AgruparConsultaCreate` puede traer selecciones
de más de un proveedor. El servicio nunca elige uno y descarta el resto
-- `pcp_consultas.proveedor_id` es una única columna NOT NULL, así que "una
consulta por proveedor" es una invariante de esquema. Se agrupa por
`proveedor_id` internamente y se crea una consulta por cada proveedor
distinto presente en la request.

Sin llamada de envío en este PR (tasks.md 9.7, "no send call yet"): `estado`
queda en `borrador` (default de columna, 0012_pcp_extras.sql M4) y
`fecha_envio` en NULL. El envío real -- `MensajeriaPort`, D9/D10 -- es PR11.
"""

from typing import Any

from supabase import Client

from services.pcp.consultas import repository as repo
from services.pcp.consultas.models import AgruparConsultaCreate
from services.pcp.documentos.port import PdfRenderer
from services.pcp.documentos.renderer_reportlab import ReportlabPdfRenderer
from services.pcp.historial import service as historial_service
from services.pcp.mensajeria.adapters import get_mensajeria
from services.pcp.mensajeria.port import MensajeAdjunto, MensajeriaPort, ResultadoEnvio
from services.pcp.negociacion import service as negociacion_service
from services.pcp.renglones import service as renglones_service
from services.productos import service as productos_service
from services.shared.database import get_service_client
from services.shared.exceptions import NotFoundError, ValidationError
from services.terceros.api import listar_contactos, obtener_proveedor_con_tercero


def agrupar_renglones(
    client: Client, *, drogueria_id: str, body: AgruparConsultaCreate, usuario_id: str
) -> list[dict[str, Any]]:
    if not body.selecciones:
        raise ValidationError("Debe seleccionarse al menos un renglón para agrupar")

    por_proveedor: dict[str, list] = {}
    for seleccion in body.selecciones:
        por_proveedor.setdefault(seleccion.proveedor_id, []).append(seleccion)

    consultas_creadas: list[dict[str, Any]] = []
    for proveedor_id, selecciones in por_proveedor.items():
        # Valida que el proveedor exista y sea del tenant -- mismo criterio
        # que catalogo/service.py::agregar_proveedor. Import directo de la
        # función (no `from services.terceros import api` como alias):
        # tests/pcp/test_dependencias.py matchea el `ast.ImportFrom.module`
        # exacto contra `services.terceros.api`, mismo gotcha ya documentado
        # en negociacion/service.py y catalogo/service.py.
        obtener_proveedor_con_tercero(client, tercero_id=proveedor_id, drogueria_id=drogueria_id)

        # Cada selección debe corresponder a una fila pcp_renglon_resultados
        # real (PR5 seleccionar_proveedores) -- si no existe,
        # obtener_resultado levanta NotFoundError; también valida
        # tenant/existencia del renglón internamente.
        resultados = [
            negociacion_service.obtener_resultado(
                client,
                drogueria_id=drogueria_id,
                pcp_renglon_id=seleccion.pcp_renglon_id,
                proveedor_id=proveedor_id,
            )
            for seleccion in selecciones
        ]

        consulta = repo.crear_consulta(
            client,
            {
                "drogueria_id": drogueria_id,
                "proveedor_id": proveedor_id,
                "contacto_id": body.contacto_id,
                "canal": body.canal,
                "fecha_respuesta_esperada": body.fecha_respuesta_esperada,
                "created_by": usuario_id,
                "updated_by": usuario_id,
            },
        )

        for seleccion, resultado in zip(selecciones, resultados):
            repo.crear_consulta_renglon(
                client,
                {
                    "drogueria_id": drogueria_id,
                    "consulta_id": consulta["id"],
                    "pcp_renglon_id": resultado["pcp_renglon_id"],
                    "cantidad_consultada": (
                        str(seleccion.cantidad_consultada)
                        if seleccion.cantidad_consultada is not None
                        else None
                    ),
                },
            )
            repo.marcar_resultado_en_consulta(
                client,
                pcp_renglon_id=resultado["pcp_renglon_id"],
                proveedor_id=proveedor_id,
                consulta_id=consulta["id"],
            )

        consultas_creadas.append(consulta)

    return consultas_creadas


def obtener_consulta(client: Client, *, consulta_id: str, drogueria_id: str) -> dict[str, Any]:
    fila = repo.buscar_consulta(client, consulta_id=consulta_id)
    if fila is None or fila["drogueria_id"] != drogueria_id:
        raise NotFoundError(f"No se encontró la consulta '{consulta_id}'")
    return fila


def listar_renglones_consulta(
    client: Client, *, consulta_id: str, drogueria_id: str
) -> list[dict[str, Any]]:
    obtener_consulta(client, consulta_id=consulta_id, drogueria_id=drogueria_id)
    return repo.listar_renglones_consulta(client, consulta_id=consulta_id)


def _armar_datos_pdf(client: Client, *, consulta_id: str, drogueria_id: str) -> dict[str, Any]:
    """Arma la estructura de datos que consume `PdfRenderer.render_consulta`
    (D9): consulta + proveedor + cada renglón agrupado, con su producto
    (cuando ya tiene matching, D2) y la cantidad consultada."""
    consulta = obtener_consulta(client, consulta_id=consulta_id, drogueria_id=drogueria_id)
    proveedor = obtener_proveedor_con_tercero(
        client, tercero_id=consulta["proveedor_id"], drogueria_id=drogueria_id
    )
    filas_consulta = repo.listar_renglones_consulta(client, consulta_id=consulta_id)

    renglones: list[dict[str, Any]] = []
    for fila in filas_consulta:
        renglon = renglones_service.obtener_renglon(
            client, renglon_id=fila["pcp_renglon_id"], drogueria_id=drogueria_id
        )
        producto = None
        if renglon.get("producto_id"):
            producto = productos_service.obtener_producto(
                client, producto_id=renglon["producto_id"], drogueria_id=drogueria_id
            )
        renglones.append(
            {
                "renglon": renglon,
                "producto": producto,
                "cantidad_consultada": fila.get("cantidad_consultada"),
            }
        )

    return {"consulta": consulta, "proveedor": proveedor, "renglones": renglones}


def generar_pdf_consulta(
    client: Client, *, consulta_id: str, drogueria_id: str, renderer: PdfRenderer | None = None
) -> bytes:
    """9.5/9.6: genera el PDF de una consulta ya agrupada. `renderer` llega
    inyectado (`PdfRenderer`, D9) -- por defecto `ReportlabPdfRenderer`, para
    que un test unitario pueda inyectar un doble sin tocar `reportlab`."""
    datos = _armar_datos_pdf(client, consulta_id=consulta_id, drogueria_id=drogueria_id)
    renderer = renderer or ReportlabPdfRenderer()
    return renderer.render_consulta(datos)


# -- 11.4-11.6 (tasks.md Fase 11): envío saliente ----------------------------
#
# El destinatario SIEMPRE se resuelve server-side desde `terceros_contactos`
# -- nunca de un valor provisto por el cliente (design.md D9/Interfaces,
# requisito de seguridad explícito, no opcional). `PCP_MENSAJERIA_ADAPTER`
# (D9) selecciona UN adaptador que implementa los dos métodos del puerto;
# "cada canal habilitado configurado" (spec) se decide acá, por los datos
# reales del contacto -- email si tiene `email`, whatsapp si tiene
# `celular`/`telefono` -- nunca por una lista de adaptadores distintos.


def _canales_disponibles(contacto: dict[str, Any]) -> list[str]:
    canales: list[str] = []
    if contacto.get("email"):
        canales.append("email")
    if contacto.get("celular") or contacto.get("telefono"):
        canales.append("whatsapp")
    return canales


def _elegir_contacto_con_datos_de_entrega(contactos: list[dict[str, Any]]) -> dict[str, Any] | None:
    utilizables = [c for c in contactos if _canales_disponibles(c)]
    if not utilizables:
        return None
    principales = [c for c in utilizables if c.get("es_principal")]
    return principales[0] if principales else utilizables[0]


def enviar_consulta(
    client: Client,
    *,
    consulta_id: str,
    drogueria_id: str,
    usuario_id: str,
    mensajeria: MensajeriaPort | None = None,
) -> dict[str, Any]:
    """11.4-11.6: entrega el PDF de una consulta ya agrupada al contacto real
    del proveedor. Spec `pcp-consultas-agrupadas`:
    - "Deliver a consulta through a configured channel": entrega por cada
      canal habilitado que el contacto realmente tenga.
    - "Reject sending without a usable contact": sin ningún contacto con
      datos de entrega, se rechaza ANTES de llamar al `MensajeriaPort` (cero
      intentos).
    - "Delivery failure does not corrupt grouping": si todos los canales
      intentados fallan, la consulta queda en `'borrador'` (nunca se
      transiciona a `'enviada'`) y `pcp_consulta_renglones` no se toca --
      reintentable con la misma consulta.
    """
    consulta = obtener_consulta(client, consulta_id=consulta_id, drogueria_id=drogueria_id)

    contactos = listar_contactos(
        client, tercero_id=consulta["proveedor_id"], drogueria_id=drogueria_id, activo=True
    )
    contacto = _elegir_contacto_con_datos_de_entrega(contactos)
    if contacto is None:
        raise ValidationError(
            f"El proveedor '{consulta['proveedor_id']}' no tiene un contacto con datos de "
            "entrega (email o teléfono) -- no se puede enviar la consulta"
        )

    pdf_bytes = generar_pdf_consulta(client, consulta_id=consulta_id, drogueria_id=drogueria_id)
    adjunto = MensajeAdjunto(nombre=f"consulta-{consulta_id}.pdf", contenido=pdf_bytes)

    mensajeria = mensajeria or get_mensajeria()
    canales = _canales_disponibles(contacto)
    resultados: list[ResultadoEnvio] = []
    if "email" in canales:
        resultados.append(
            mensajeria.enviar_email(
                destinatario=contacto["email"],
                asunto="Consulta de cotización",
                cuerpo="Le solicitamos cotización para los productos adjuntos.",
                adjuntos=[adjunto],
            )
        )
    if "whatsapp" in canales:
        resultados.append(
            mensajeria.enviar_whatsapp(
                destinatario=contacto.get("celular") or contacto["telefono"],
                plantilla="consulta_pcp",
                variables={"consulta_id": consulta_id},
                adjuntos=[adjunto],
            )
        )

    if all(r.error is not None for r in resultados):
        errores = [r.error for r in resultados]
        raise ValidationError(
            f"No se pudo entregar la consulta '{consulta_id}' por ningún canal configurado: {errores}"
        )

    consulta_actualizada = repo.marcar_enviada(client, consulta_id=consulta_id)

    # D6: un evento por cada PCP de origen involucrado -- pcp_historial.pcp_id
    # es NOT NULL (0012_pcp_extras.sql M1) y una consulta agrupa renglones de
    # varios PCPs (D9, sin pcp_id propio), así que no hay un único pcp_id al
    # que asociar el evento.
    filas_renglones = repo.listar_renglones_consulta(client, consulta_id=consulta_id)
    pcp_ids = {
        renglones_service.obtener_renglon(
            client, renglon_id=fila["pcp_renglon_id"], drogueria_id=drogueria_id
        )["pcp_id"]
        for fila in filas_renglones
    }
    for pcp_id in pcp_ids:
        historial_service.agregar_evento(
            client,
            drogueria_id=drogueria_id,
            pcp_id=pcp_id,
            tipo_evento="consulta_enviada",
            payload={"consulta_id": consulta_id, "proveedor_id": consulta["proveedor_id"], "canales": canales},
            usuario_id=usuario_id,
        )

    return consulta_actualizada


# -- wrappers de endpoint (service_role, mismo criterio que
# services/pcp/negociacion/service.py::*_para_endpoint) -----------------------


def agrupar_renglones_para_endpoint(
    *, drogueria_id: str, body: AgruparConsultaCreate, usuario_id: str
) -> list[dict[str, Any]]:
    return agrupar_renglones(
        get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id
    )


def obtener_consulta_para_endpoint(*, consulta_id: str, drogueria_id: str) -> dict[str, Any]:
    return obtener_consulta(get_service_client(), consulta_id=consulta_id, drogueria_id=drogueria_id)


def generar_pdf_consulta_para_endpoint(*, consulta_id: str, drogueria_id: str) -> bytes:
    return generar_pdf_consulta(get_service_client(), consulta_id=consulta_id, drogueria_id=drogueria_id)


def enviar_consulta_para_endpoint(
    *, consulta_id: str, drogueria_id: str, usuario_id: str
) -> dict[str, Any]:
    return enviar_consulta(
        get_service_client(), consulta_id=consulta_id, drogueria_id=drogueria_id, usuario_id=usuario_id
    )
