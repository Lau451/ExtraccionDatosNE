"""Tests para services/shared/http_client.py — httpx.Client resiliente para Supabase.

Root cause (T5, ver odd/tasks/extraccion-multi-tenant.md y el docstring de
services/shared/http_client.py): postgrest-py fuerza http2=True en el httpx.Client
que construye internamente. httpcore SÍ detecta proactivamente una conexión que el
servidor cerró mientras estaba idle -- pero solo en su implementación HTTP/1.1
(has_expired() en httpcore/_sync/http11.py hace un peek no bloqueante del socket:
"is_readable mientras el estado es IDLE" == el server mandó EOF). La implementación
HTTP/2 (httpcore/_sync/http2.py::has_expired) NO hace ese peek, solo compara contra
el timer de keepalive_expiry. Con Supabase/Cloudflare cortando la conexión mientras
el proceso está ocupado (~50s de Gemini), el siguiente pedido reusa la conexión HTTP/2
ya muerta y explota con httpx.RemoteProtocolError("Server disconnected"). Desactivar
HTTP/2 hace que httpcore detecte la desconexión y abra una conexión nueva en vez de
reusar la muerta -- sin retries ni estado adicional.
"""
import httpx

from services.shared.http_client import build_resilient_httpx_client


def test_build_resilient_httpx_client_disables_http2():
    """HTTP/2 deshabilitado -> httpcore usa su ruta HTTP/1.1, que sí detecta un
    socket cerrado por el server mientras estaba idle antes de reusarlo."""
    client = build_resilient_httpx_client()

    assert isinstance(client, httpx.Client)
    assert client._transport._pool._http2 is False


def test_build_resilient_httpx_client_returns_new_instance_each_call():
    """Cada llamada crea un httpx.Client propio -- se inyecta uno por cada
    supabase.Client (ver services/extraccion/supabase_client.py y
    services/shared/database.py); nunca se comparte una instancia global."""
    a = build_resilient_httpx_client()
    b = build_resilient_httpx_client()

    assert a is not b
