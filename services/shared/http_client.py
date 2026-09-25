"""Fábrica de httpx.Client resiliente para los clientes Supabase — services/shared/http_client.py

Root cause (T5, 2026-09-25, ver odd/tasks/extraccion-multi-tenant.md): postgrest-py fuerza
http2=True en el httpx.Client que construye internamente (postgrest/_sync/client.py,
SyncPostgrestClient.__init__) y no expone ningún flag para desactivarlo.

httpcore SÍ detecta proactivamente una conexión que el servidor cerró mientras estaba
idle -- pero solo en su implementación HTTP/1.1: `has_expired()` en
httpcore/_sync/http11.py hace un peek no bloqueante del socket ("is_readable" mientras
el estado es IDLE solo puede significar que el server mandó EOF) además de comparar
contra el timer de `keepalive_expiry`. La implementación HTTP/2
(httpcore/_sync/http2.py::has_expired) NO hace ese peek: solo compara contra el timer.

Con Supabase/Cloudflare cortando la conexión pooled mientras el proceso está ocupado
(p.ej. ~50s de Gemini procesando una orden de compra), el siguiente pedido reusa la
conexión HTTP/2 ya muerta y explota con `httpx.RemoteProtocolError("Server
disconnected")` -- exactamente el síntoma observado el 2026-09-25 (POST /procesar OK,
cerrar_sesion y el siguiente GET /api/documentos fallando con 500/503).

Fix elegido: construir el httpx.Client explícitamente con http2=False e inyectarlo vía
`supabase.ClientOptions(httpx_client=...)` en cada `create_client(...)`. Con HTTP/1.1,
httpcore detecta la desconexión y abre una conexión nueva en vez de reusar la muerta --
sin retries ni estado adicional, y sin riesgo de duplicar un INSERT no idempotente (a
diferencia de un retry transparente, que solo sería seguro para lecturas). Se descartó
un retry genérico sobre httpx.RemoteProtocolError/ReadError/ConnectError porque el
propio postgrest-py ya tiene un `send_with_retry` (ver postgrest/_sync/request_builder.py)
que solo reintenta GET/HEAD ante 503/520 de Cloudflare -- agregar un segundo mecanismo de
retry por fuera duplicaría esa responsabilidad sin resolver la causa raíz (la conexión
HTTP/2 muerta seguiría reusándose en cada intento).

Compartido entre services/extraccion/ y services/shared/database.py (services/presupuestacion/
y services/terceros/ vía get_user_client/get_service_client) porque ambos servicios pegan
al mismo proyecto Supabase con el mismo patrón de cliente pooled de larga vida -- un único
lugar para no duplicar el mismo fix dos veces.

Al inyectar un cliente, postgrest-py deja de construir el suyo, así que hay que
replicar a mano lo que ese cliente traía: DEFAULT_POSTGREST_CLIENT_TIMEOUT (sin
esto queda el timeout por defecto de httpx, 5 s) y follow_redirects=True.
base_url y headers NO hacen falta: postgrest y auth arman la URL absoluta y
mandan los headers en cada request, sin mutar el cliente inyectado.
"""
import httpx
from postgrest.constants import DEFAULT_POSTGREST_CLIENT_TIMEOUT


def build_resilient_httpx_client() -> httpx.Client:
    """Nuevo httpx.Client con HTTP/2 desactivado, para inyectar en
    supabase.ClientOptions(httpx_client=...). Una instancia nueva por cada
    supabase.Client construido -- nunca se comparte un pool de conexiones entre
    clientes con ciclos de vida distintos (singleton de servicio vs. cache por
    token de usuario)."""
    return httpx.Client(
        http2=False,
        timeout=httpx.Timeout(DEFAULT_POSTGREST_CLIENT_TIMEOUT),
        follow_redirects=True,
    )
