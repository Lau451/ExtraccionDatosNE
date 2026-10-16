import ssl

import certifi
import pytest

from services.shared.auth_jwt import TokenInvalidoError, _jwk_client, verificar_token


def test_verificar_token_con_token_malformado_levanta_token_invalido():
    """Un token que ni siquiera tiene la forma de un JWT falla al decodificar el
    header (para resolver 'kid') antes de llegar a pedir el JWKS por red -- no hace
    falta mockear nada para ejercitar esta rama."""
    with pytest.raises(TokenInvalidoError):
        verificar_token("esto-no-es-un-jwt", supabase_url="https://example.supabase.co")


def test_jwk_client_verifica_tls_con_el_bundle_de_certifi():
    """El JWKS se baja con urllib, que en Windows usa el almacen de certificados del
    sistema. En la imagen windowsservercore ese almacen no tiene la CA de Supabase
    (CERTIFICATE_VERIFY_FAILED), y cada login terminaba en 'Token invalido o
    vencido'. El cliente tiene que verificar contra el bundle de certifi."""
    client = _jwk_client("https://certifi-check.supabase.co")

    contexto = client.ssl_context
    assert contexto is not None
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    assert contexto.check_hostname is True
    esperado = ssl.create_default_context(cafile=certifi.where())
    assert len(contexto.get_ca_certs()) == len(esperado.get_ca_certs())
