import pytest

from services.shared.auth_jwt import TokenInvalidoError, verificar_token


def test_verificar_token_con_token_malformado_levanta_token_invalido():
    """Un token que ni siquiera tiene la forma de un JWT falla al decodificar el
    header (para resolver 'kid') antes de llegar a pedir el JWKS por red -- no hace
    falta mockear nada para ejercitar esta rama."""
    with pytest.raises(TokenInvalidoError):
        verificar_token("esto-no-es-un-jwt", supabase_url="https://example.supabase.co")
