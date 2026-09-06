"""11.4-11.6 (openspec/changes/gestor-pcp/tasks.md Fase 11) --
pcp-consultas-agrupadas, envío saliente: `enviar_consulta` resuelve el
destinatario desde `terceros_contactos` del servidor -- nunca de un valor
provisto por el cliente (design.md D9/Interfaces) -- y entrega a través de
cada canal habilitado (email si el contacto tiene `email`, whatsapp si tiene
`celular`/`telefono`) usando el `MensajeriaPort` inyectado (por defecto
`get_mensajeria()`, D9).

RED hasta que 11.6 cree `services/pcp/consultas/service.py::enviar_consulta`.
"""

from typing import Any

import pytest

from services.pcp.consultas.models import AgruparConsultaCreate, SeleccionParaAgrupar
from services.pcp.consultas.service import agrupar_renglones, enviar_consulta, obtener_consulta
from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.mensajeria.port import ResultadoEnvio
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon, seleccionar_proveedores
from services.shared.exceptions import ValidationError


class _MensajeriaFalsa:
    """Doble de prueba de `MensajeriaPort` (Protocol estructural, D9) -- sin
    mocks: registra cada llamada real para poder afirmar "cada canal
    habilitado fue invocado" y "cero intentos" según el escenario."""

    def __init__(self, *, entregado: bool = True, error: str | None = None) -> None:
        self._entregado = entregado
        self._error = error
        self.llamadas_email: list[dict[str, Any]] = []
        self.llamadas_whatsapp: list[dict[str, Any]] = []

    def enviar_email(self, *, destinatario, asunto, cuerpo, adjuntos=()):
        self.llamadas_email.append({"destinatario": destinatario, "asunto": asunto, "adjuntos": adjuntos})
        return ResultadoEnvio(entregado=self._entregado, proveedor_externo="falso", error=self._error)

    def enviar_whatsapp(self, *, destinatario, plantilla, variables, adjuntos=()):
        self.llamadas_whatsapp.append({"destinatario": destinatario, "plantilla": plantilla})
        return ResultadoEnvio(entregado=self._entregado, proveedor_externo="falso", error=self._error)


def _crear_consulta(
    service_client, *, drogueria_id, presupuesto_id, item_proceso_id, usuario_id, proveedor_id
):
    pcp = crear_pcp(
        service_client,
        drogueria_id=drogueria_id,
        body=PcpCreate(presupuesto_id=presupuesto_id),
        usuario_id=usuario_id,
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=drogueria_id,
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item_proceso_id),
        usuario_id=usuario_id,
    )
    seleccionar_proveedores(
        service_client, renglon_id=renglon["id"], drogueria_id=drogueria_id, proveedor_ids=[proveedor_id]
    )
    consultas = agrupar_renglones(
        service_client,
        drogueria_id=drogueria_id,
        body=AgruparConsultaCreate(
            selecciones=[SeleccionParaAgrupar(pcp_renglon_id=renglon["id"], proveedor_id=proveedor_id)]
        ),
        usuario_id=usuario_id,
    )
    return pcp, consultas[0]


# ---------------------------------------------------------------------------
# 11.5 -- entrega por cada canal habilitado configurado
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_enviar_consulta_entrega_por_cada_canal_habilitado(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    contacto = (
        service_client.table("terceros_contactos")
        .insert(
            {
                "tercero_id": seed_proveedor_pcp["id"],
                "drogueria_id": seed_drogueria["id"],
                "nombre": "Contacto Proveedor",
                "email": "compras@proveedor-test.local",
                "celular": "+5493410000001",
                "es_principal": True,
            }
        )
        .execute()
        .data[0]
    )
    pcp, consulta = _crear_consulta(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_id=seed_proveedor_pcp["id"],
    )

    try:
        mensajeria = _MensajeriaFalsa(entregado=True)
        actualizada = enviar_consulta(
            service_client,
            consulta_id=consulta["id"],
            drogueria_id=seed_drogueria["id"],
            usuario_id=seed_usuario_sistema["id"],
            mensajeria=mensajeria,
        )

        # Ambos canales habilitados por los datos del contacto (email +
        # celular) fueron invocados -- no solo uno.
        assert len(mensajeria.llamadas_email) == 1
        assert mensajeria.llamadas_email[0]["destinatario"] == "compras@proveedor-test.local"
        assert len(mensajeria.llamadas_whatsapp) == 1
        assert mensajeria.llamadas_whatsapp[0]["destinatario"] == "+5493410000001"

        assert actualizada["estado"] == "enviada"
        assert actualizada["fecha_envio"] is not None

        en_bd = obtener_consulta(service_client, consulta_id=consulta["id"], drogueria_id=seed_drogueria["id"])
        assert en_bd["estado"] == "enviada"
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("pcp_consultas").delete().eq("id", consulta["id"]).execute()
        service_client.table("terceros_contactos").delete().eq("id", contacto["id"]).execute()


# ---------------------------------------------------------------------------
# 11.5 -- sin contacto con datos de entrega: rechazo, cero intentos
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_enviar_consulta_sin_contacto_con_datos_de_entrega_es_rechazada_sin_intentar(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, consulta = _crear_consulta(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_id=seed_proveedor_pcp["id"],
    )

    try:
        # Deliberadamente NO se crea ningún terceros_contactos para el
        # proveedor -- ninguna dirección de entrega existe.
        mensajeria = _MensajeriaFalsa(entregado=True)
        with pytest.raises(ValidationError):
            enviar_consulta(
                service_client,
                consulta_id=consulta["id"],
                drogueria_id=seed_drogueria["id"],
                usuario_id=seed_usuario_sistema["id"],
                mensajeria=mensajeria,
            )

        assert mensajeria.llamadas_email == []
        assert mensajeria.llamadas_whatsapp == []

        en_bd = obtener_consulta(service_client, consulta_id=consulta["id"], drogueria_id=seed_drogueria["id"])
        assert en_bd["estado"] == "borrador"
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("pcp_consultas").delete().eq("id", consulta["id"]).execute()


# ---------------------------------------------------------------------------
# 11.5 -- una falla de entrega no corrompe la agrupación: reintentable
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_enviar_consulta_con_falla_de_entrega_deja_consulta_y_agrupacion_intactas_para_reintentar(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    contacto = (
        service_client.table("terceros_contactos")
        .insert(
            {
                "tercero_id": seed_proveedor_pcp["id"],
                "drogueria_id": seed_drogueria["id"],
                "nombre": "Contacto Proveedor",
                "email": "compras@proveedor-test.local",
                "es_principal": True,
            }
        )
        .execute()
        .data[0]
    )
    pcp, consulta = _crear_consulta(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_id=seed_proveedor_pcp["id"],
    )

    try:
        mensajeria_falla = _MensajeriaFalsa(entregado=False, error="Vendor no disponible")
        with pytest.raises(Exception):
            enviar_consulta(
                service_client,
                consulta_id=consulta["id"],
                drogueria_id=seed_drogueria["id"],
                usuario_id=seed_usuario_sistema["id"],
                mensajeria=mensajeria_falla,
            )

        en_bd = obtener_consulta(service_client, consulta_id=consulta["id"], drogueria_id=seed_drogueria["id"])
        assert en_bd["estado"] == "borrador"
        # La agrupación (renglones -> consulta) sigue intacta -- ningún
        # renglón se descarta silenciosamente por la falla.
        filas = (
            service_client.table("pcp_consulta_renglones")
            .select("id")
            .eq("consulta_id", consulta["id"])
            .execute()
            .data
        )
        assert len(filas) == 1

        # Reintento con un adaptador que sí entrega: ahora sí transiciona.
        mensajeria_ok = _MensajeriaFalsa(entregado=True)
        actualizada = enviar_consulta(
            service_client,
            consulta_id=consulta["id"],
            drogueria_id=seed_drogueria["id"],
            usuario_id=seed_usuario_sistema["id"],
            mensajeria=mensajeria_ok,
        )
        assert actualizada["estado"] == "enviada"
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("pcp_consultas").delete().eq("id", consulta["id"]).execute()
        service_client.table("terceros_contactos").delete().eq("id", contacto["id"]).execute()
