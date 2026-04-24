"""
Tests para generate_with_fallback: si gemini-2.5-flash falla,
debe redirigir automáticamente a gemini-3-flash-preview.
"""

import pytest
from unittest.mock import MagicMock, call, patch

from app.config import generate_with_fallback, PRIMARY_MODEL, FALLBACK_MODEL


def _mock_client(side_effects):
    client = MagicMock()
    client.models.generate_content.side_effect = side_effects
    return client


def test_usa_modelo_primario_cuando_funciona():
    respuesta = MagicMock()
    client = _mock_client([respuesta])

    resultado = generate_with_fallback(client, "contenido")

    assert resultado is respuesta
    client.models.generate_content.assert_called_once_with(
        model=PRIMARY_MODEL, contents="contenido"
    )


def test_usa_fallback_cuando_primario_falla():
    respuesta_fallback = MagicMock()
    client = _mock_client([Exception("503 Service Unavailable"), respuesta_fallback])

    resultado = generate_with_fallback(client, "contenido")

    assert resultado is respuesta_fallback
    assert client.models.generate_content.call_count == 2
    assert client.models.generate_content.call_args_list == [
        call(model=PRIMARY_MODEL, contents="contenido"),
        call(model=FALLBACK_MODEL, contents="contenido"),
    ]


def test_fallback_con_rate_limit():
    respuesta_fallback = MagicMock()
    client = _mock_client([Exception("429 Resource exhausted"), respuesta_fallback])

    resultado = generate_with_fallback(client, "contenido")

    assert resultado is respuesta_fallback
    assert client.models.generate_content.call_args_list[1] == call(
        model=FALLBACK_MODEL, contents="contenido"
    )


def test_fallback_con_timeout():
    respuesta_fallback = MagicMock()
    client = _mock_client([TimeoutError("deadline exceeded"), respuesta_fallback])

    resultado = generate_with_fallback(client, "contenido")

    assert resultado is respuesta_fallback


def test_loguea_warning_cuando_usa_fallback(caplog):
    import logging
    respuesta_fallback = MagicMock()
    client = _mock_client([Exception("503 Service Unavailable"), respuesta_fallback])

    with caplog.at_level(logging.WARNING, logger="app.config"):
        generate_with_fallback(client, "contenido")

    assert any(PRIMARY_MODEL in msg for msg in caplog.messages)
    assert any(FALLBACK_MODEL in msg for msg in caplog.messages)


def test_no_usa_fallback_si_primario_funciona():
    respuesta = MagicMock()
    client = _mock_client([respuesta])

    generate_with_fallback(client, "contenido")

    assert client.models.generate_content.call_count == 1


@pytest.mark.parametrize("contents", [
    "texto simple",
    ["prompt", MagicMock()],
    "prompt\n\nmarkdown largo",
])
def test_pasa_contents_correctamente_al_fallback(contents):
    respuesta_fallback = MagicMock()
    client = _mock_client([Exception("fallo"), respuesta_fallback])

    generate_with_fallback(client, contents)

    _, kwargs = client.models.generate_content.call_args_list[1]
    assert kwargs["contents"] is contents
