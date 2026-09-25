from types import SimpleNamespace

import services.shared.database as database


def _parchear_settings(monkeypatch):
    monkeypatch.setattr(
        database,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-key-de-test",
        ),
    )


def test_get_user_client_mismo_token_reusa_la_misma_instancia(monkeypatch):
    """Antes, get_user_client() creaba un Client (y su httpx.Client interno) nuevo
    en cada llamada -- pagando de nuevo el handshake TLS a Supabase por request
    (~500ms medidos en vivo, ver mem discovery "PCP delay"). Cachear por token
    reusa la conexión ya caliente entre llamadas del mismo usuario/sesión."""
    _parchear_settings(monkeypatch)
    database._cliente_por_token.cache_clear()

    cliente_a = database.get_user_client(token="token-usuario-a")
    cliente_a_de_nuevo = database.get_user_client(token="token-usuario-a")

    assert cliente_a is cliente_a_de_nuevo


def test_get_user_client_tokens_distintos_nunca_comparten_instancia(monkeypatch):
    """SyncPostgrestClient.auth() escribe el header Authorization en el propio
    objeto Client (headers["Authorization"] = f"Bearer {token}"). Si dos tokens
    distintos compartieran una instancia cacheada, el pedido de un usuario podría
    salir con el token de otro -- por eso el cache es por token, nunca global."""
    _parchear_settings(monkeypatch)
    database._cliente_por_token.cache_clear()

    cliente_a = database.get_user_client(token="token-usuario-a")
    cliente_b = database.get_user_client(token="token-usuario-b")

    assert cliente_a is not cliente_b
    assert cliente_a.postgrest.headers["Authorization"] == "Bearer token-usuario-a"
    assert cliente_b.postgrest.headers["Authorization"] == "Bearer token-usuario-b"


def test_get_user_client_disables_http2(monkeypatch):
    """T5 (odd/tasks/extraccion-multi-tenant.md): sin esto, postgrest-py fuerza
    http2=True y una conexión que Supabase cerró en un idle largo se reusa muerta
    en el siguiente pedido -> httpx.RemoteProtocolError("Server disconnected").
    Ver services/shared/http_client.py."""
    _parchear_settings(monkeypatch)
    database._cliente_por_token.cache_clear()

    cliente = database.get_user_client(token="token-http2-test")

    assert cliente.postgrest.session._transport._pool._http2 is False


def test_get_service_client_disables_http2(monkeypatch):
    """Mismo fix que get_user_client(), para el cliente service-role."""
    monkeypatch.setattr(
        database,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_key="service-key-de-test",
        ),
    )
    database.get_service_client.cache_clear()

    cliente = database.get_service_client()

    assert cliente.postgrest.session._transport._pool._http2 is False
