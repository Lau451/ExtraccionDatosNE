"""11.7-11.11 (openspec/changes/gestor-pcp/tasks.md Fase 11, design.md D10) --
`negociacion/service.py::cerrar_pcp`: cierra un PCP delegando la transición
real en `gestion_service.cambiar_estado` (reusa la máquina de estados
existente) y ejecuta el feedback loop Comercial en dos fases:

- Fase A (siempre activa): renderiza el PDF de resultado y lo manda por
  email a `usuarios.email` del `pcp.solicitante_id` (spec `pcp-sugerencias`,
  "Comercial Feedback Loop -- Email Phase").
- Fase B (`PCP_REPRICING_AUTOMATICO`, default apagado): notificación interna
  (`TipoNotificacion.pcp_cerrada`) + repricing automático vía
  `pricing.service.generar_presupuesto_para_endpoint`, solo si el
  presupuesto de origen sigue `generado`/`en_revision` (spec
  `pcp-sugerencias`, "...Internal Notification and Auto-Repricing Phase").

RED hasta que 11.7/11.11 implementen `cerrar_pcp` con ambas fases.
"""

from datetime import datetime, timezone
from typing import Any

import pytest

from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import cambiar_estado, crear_pcp
from services.pcp.mensajeria.port import MensajeAdjunto, ResultadoEnvio
from services.pcp.negociacion.service import cerrar_pcp
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon
from services.shared.config import get_settings
from services.shared.exceptions import ValidationError


class _MensajeriaFalsa:
    def __init__(self) -> None:
        self.llamadas: list[dict[str, Any]] = []

    def enviar_email(self, *, destinatario, asunto, cuerpo, adjuntos=()):
        self.llamadas.append(
            {"destinatario": destinatario, "asunto": asunto, "cuerpo": cuerpo, "adjuntos": adjuntos}
        )
        return ResultadoEnvio(entregado=True, proveedor_externo="falso")

    def enviar_whatsapp(self, *, destinatario, plantilla, variables, adjuntos=()):  # pragma: no cover
        raise AssertionError("cerrar_pcp no debería usar whatsapp")


def _crear_pcp_esperando_respuesta(
    service_client, *, drogueria_id, presupuesto_id, item_proceso_id, usuario_id, solicitante_id
):
    pcp = crear_pcp(
        service_client,
        drogueria_id=drogueria_id,
        body=PcpCreate(presupuesto_id=presupuesto_id, solicitante_id=solicitante_id),
        usuario_id=usuario_id,
    )
    crear_renglon(
        service_client,
        drogueria_id=drogueria_id,
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item_proceso_id),
        usuario_id=usuario_id,
    )
    cambiar_estado(
        service_client,
        pcp_id=pcp["id"],
        drogueria_id=drogueria_id,
        estado_nuevo="en_gestion",
        usuario_id=usuario_id,
    )
    cambiar_estado(
        service_client,
        pcp_id=pcp["id"],
        drogueria_id=drogueria_id,
        estado_nuevo="esperando_respuesta",
        usuario_id=usuario_id,
    )
    return pcp


# ---------------------------------------------------------------------------
# 11.8 -- cerrar un PCP emails el resultado al usuario solicitante
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cerrar_pcp_emails_resultado_al_solicitante(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_solicitante_pcp,
    seed_item_proceso,
    seed_presupuesto_factory,
):
    presupuesto = seed_presupuesto_factory()
    pcp = _crear_pcp_esperando_respuesta(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        solicitante_id=seed_solicitante_pcp["id"],
    )

    try:
        mensajeria = _MensajeriaFalsa()
        actualizado = cerrar_pcp(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
            usuario_id=seed_usuario_sistema["id"],
            mensajeria=mensajeria,
        )

        assert actualizado["estado"] == "cerrada"
        assert len(mensajeria.llamadas) == 1
        llamada = mensajeria.llamadas[0]
        assert llamada["destinatario"] == seed_solicitante_pcp["email"]
        adjuntos: list[MensajeAdjunto] = llamada["adjuntos"]
        assert len(adjuntos) == 1
        assert adjuntos[0].contenido[:4] == b"%PDF"

        eventos = (
            service_client.table("pcp_historial")
            .select("tipo_evento")
            .eq("pcp_id", pcp["id"])
            .eq("tipo_evento", "notificacion_enviada")
            .execute()
            .data
        )
        assert len(eventos) == 1
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_cerrar_pcp_sin_solicitante_lanza_validation_error(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
):
    """Triangulación: un PCP sin `solicitante_id` no tiene a quién notificar
    -- `cerrar_pcp` rechaza antes de intentar ningún envío (nunca deja el
    PCP en un estado 'cerrada' silenciosamente sin feedback loop)."""
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    cambiar_estado(
        service_client,
        pcp_id=pcp["id"],
        drogueria_id=seed_drogueria["id"],
        estado_nuevo="en_gestion",
        usuario_id=seed_usuario_sistema["id"],
    )
    cambiar_estado(
        service_client,
        pcp_id=pcp["id"],
        drogueria_id=seed_drogueria["id"],
        estado_nuevo="esperando_respuesta",
        usuario_id=seed_usuario_sistema["id"],
    )

    try:
        mensajeria = _MensajeriaFalsa()
        with pytest.raises(ValidationError):
            cerrar_pcp(
                service_client,
                pcp_id=pcp["id"],
                drogueria_id=seed_drogueria["id"],
                usuario_id=seed_usuario_sistema["id"],
                mensajeria=mensajeria,
            )
        assert mensajeria.llamadas == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# 11.10/11.11 -- notificación interna + repricing automático (flag on)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cerrar_pcp_con_flag_activo_y_presupuesto_abierto_notifica_y_repricea(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_solicitante_pcp,
    seed_item_proceso,
    seed_presupuesto_factory,
    monkeypatch,
):
    presupuesto = seed_presupuesto_factory(estado="generado")
    pcp = _crear_pcp_esperando_respuesta(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        solicitante_id=seed_solicitante_pcp["id"],
    )

    get_settings.cache_clear()
    monkeypatch.setenv("PCP_REPRICING_AUTOMATICO", "true")
    try:
        cerrar_pcp(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
            usuario_id=seed_usuario_sistema["id"],
            mensajeria=_MensajeriaFalsa(),
        )

        notificaciones = (
            service_client.table("notificaciones")
            .select("*")
            .eq("destinatario_id", seed_solicitante_pcp["id"])
            .eq("tipo", "pcp_cerrada")
            .execute()
            .data
        )
        assert len(notificaciones) == 1

        # El repricing automático corrió de verdad sobre el presupuesto de
        # origen: pasó de 0 a 1 ítem procesado (mismo proceso_comercial_id
        # que seed_item_proceso), no solo "no lanzó excepción".
        presupuesto_en_bd = (
            service_client.table("presupuestos").select("*").eq("id", presupuesto["id"]).execute().data[0]
        )
        assert presupuesto_en_bd["cantidad_items"] == 1
    finally:
        monkeypatch.delenv("PCP_REPRICING_AUTOMATICO", raising=False)
        get_settings.cache_clear()
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("notificaciones").delete().eq(
            "destinatario_id", seed_solicitante_pcp["id"]
        ).execute()
        service_client.table("presupuesto_items").delete().eq(
            "presupuesto_id", presupuesto["id"]
        ).execute()


@pytest.mark.integration
def test_cerrar_pcp_con_flag_activo_y_presupuesto_ya_no_abierto_notifica_pero_no_repricea(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_solicitante_pcp,
    seed_item_proceso,
    seed_presupuesto_factory,
    monkeypatch,
):
    # ck_pre_aprobado (docs/schema/extractor_final.sql) exige aprobado_at +
    # aprobado_por para cualquier estado fuera de generado/en_revision/vencido.
    presupuesto = seed_presupuesto_factory(
        estado="aprobado",
        aprobado_at=datetime.now(timezone.utc).isoformat(),
        aprobado_por=seed_usuario_sistema["id"],
    )
    pcp = _crear_pcp_esperando_respuesta(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        solicitante_id=seed_solicitante_pcp["id"],
    )

    get_settings.cache_clear()
    monkeypatch.setenv("PCP_REPRICING_AUTOMATICO", "true")
    try:
        cerrar_pcp(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
            usuario_id=seed_usuario_sistema["id"],
            mensajeria=_MensajeriaFalsa(),
        )

        notificaciones = (
            service_client.table("notificaciones")
            .select("*")
            .eq("destinatario_id", seed_solicitante_pcp["id"])
            .eq("tipo", "pcp_cerrada")
            .execute()
            .data
        )
        # La notificación interna se sigue emitiendo aunque no se repricee.
        assert len(notificaciones) == 1

        presupuesto_en_bd = (
            service_client.table("presupuestos").select("*").eq("id", presupuesto["id"]).execute().data[0]
        )
        # Nunca se tocó: seed_presupuesto_factory lo crea con cantidad_items=0.
        assert presupuesto_en_bd["cantidad_items"] == 0
    finally:
        monkeypatch.delenv("PCP_REPRICING_AUTOMATICO", raising=False)
        get_settings.cache_clear()
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("notificaciones").delete().eq(
            "destinatario_id", seed_solicitante_pcp["id"]
        ).execute()


@pytest.mark.integration
def test_cerrar_pcp_con_flag_apagado_no_notifica_ni_repricea(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_solicitante_pcp,
    seed_item_proceso,
    seed_presupuesto_factory,
):
    """Triangulación respecto a los dos tests anteriores: con el flag en su
    default (apagado), la Fase B entera queda inactiva -- ni notificación ni
    repricing, sin necesidad de setear PCP_REPRICING_AUTOMATICO."""
    presupuesto = seed_presupuesto_factory(estado="generado")
    pcp = _crear_pcp_esperando_respuesta(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        solicitante_id=seed_solicitante_pcp["id"],
    )

    try:
        assert get_settings().pcp_repricing_automatico is False

        cerrar_pcp(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
            usuario_id=seed_usuario_sistema["id"],
            mensajeria=_MensajeriaFalsa(),
        )

        notificaciones = (
            service_client.table("notificaciones")
            .select("*")
            .eq("destinatario_id", seed_solicitante_pcp["id"])
            .eq("tipo", "pcp_cerrada")
            .execute()
            .data
        )
        assert notificaciones == []

        presupuesto_en_bd = (
            service_client.table("presupuestos").select("*").eq("id", presupuesto["id"]).execute().data[0]
        )
        assert presupuesto_en_bd["cantidad_items"] == 0
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
