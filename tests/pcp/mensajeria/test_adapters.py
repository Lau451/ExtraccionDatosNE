"""11.1-11.2 (openspec/changes/gestor-pcp/tasks.md Fase 11) -- puerto de
mensajeria de PCP: `LoggingMensajeriaAdapter` (default, D9) nunca entrega de
verdad -- registra `ResultadoEnvio(entregado=False, proveedor_externo="log")`
sin llamar a ningun vendor -- y `get_mensajeria()` resuelve el adaptador desde
`PCP_MENSAJERIA_ADAPTER` (default "log").

RED hasta que 11.1/11.2 creen `services/pcp/mensajeria/{port,adapters}.py`.
Unit test puro -- sin base de datos: `LoggingMensajeriaAdapter` no toca
Supabase ni ningun servicio externo, mismo criterio que cualquier test de
lógica pura del proyecto (p.ej. `PdfRenderer` triangulado en PR9 sí necesita
la base para armar datos, pero el adapter en sí no).
"""

from services.pcp.mensajeria.adapters import LoggingMensajeriaAdapter, get_mensajeria
from services.pcp.mensajeria.port import MensajeAdjunto, ResultadoEnvio


def test_logging_adapter_enviar_email_no_entrega_y_queda_registrado():
    adapter = LoggingMensajeriaAdapter()

    resultado = adapter.enviar_email(
        destinatario="proveedor@example.com",
        asunto="Consulta de cotización",
        cuerpo="Cuerpo del mensaje",
    )

    assert isinstance(resultado, ResultadoEnvio)
    assert resultado.entregado is False
    assert resultado.proveedor_externo == "log"
    assert resultado.error is None


def test_logging_adapter_enviar_whatsapp_no_entrega_y_queda_registrado():
    adapter = LoggingMensajeriaAdapter()

    resultado = adapter.enviar_whatsapp(
        destinatario="+5493410000000",
        plantilla="consulta_pcp",
        variables={"consulta_id": "abc"},
        adjuntos=[MensajeAdjunto(nombre="consulta.pdf", contenido=b"%PDF-1.4")],
    )

    # Triangulación respecto al test anterior: distinto método, distinto
    # canal, mismo resultado honesto de "no vendor configurado" (D9).
    assert resultado.entregado is False
    assert resultado.proveedor_externo == "log"


def test_get_mensajeria_default_devuelve_logging_adapter(monkeypatch):
    from services.shared.config import get_settings

    get_settings.cache_clear()
    monkeypatch.delenv("PCP_MENSAJERIA_ADAPTER", raising=False)
    try:
        adapter = get_mensajeria()
        assert isinstance(adapter, LoggingMensajeriaAdapter)
        # Satisface estructuralmente `MensajeriaPort` (Protocol, design.md
        # D9): ambos métodos del puerto están presentes y devuelven
        # `ResultadoEnvio` real.
        resultado = adapter.enviar_email(destinatario="x@example.com", asunto="a", cuerpo="b")
        assert isinstance(resultado, ResultadoEnvio)
    finally:
        get_settings.cache_clear()


def test_get_mensajeria_con_adaptador_no_soportado_lanza_value_error(monkeypatch):
    from services.shared.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PCP_MENSAJERIA_ADAPTER", "vendor_inexistente")
    try:
        import pytest

        with pytest.raises(ValueError):
            get_mensajeria()
    finally:
        monkeypatch.delenv("PCP_MENSAJERIA_ADAPTER", raising=False)
        get_settings.cache_clear()
