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
