"""
Tests para services/extraccion/supabase_client.py — Feature flag + singleton.

Verifica:
- ENABLE_RESULT_PERSISTENCE=false → retorna None
- Variables faltantes → retorna None sin crash
- Variables presentes → retorna Client singleton
- Dos llamadas → mismo objeto (singleton pattern)
"""

import pytest
from unittest.mock import MagicMock
import services.extraccion.supabase_client as sc_module


@pytest.fixture(autouse=True)
def reset_singleton():
    """Resetea el singleton antes de cada test para evitar estado compartido."""
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()


class TestFeatureFlag:
    """Tests del feature flag ENABLE_RESULT_PERSISTENCE."""

    def test_get_client_disabled(self, monkeypatch):
        """Cuando ENABLE_RESULT_PERSISTENCE=false → get_client() retorna None."""
        monkeypatch.setenv("ENABLE_RESULT_PERSISTENCE", "false")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-key")

        resultado = sc_module.get_client()

        assert resultado is None

    def test_get_client_disabled_uppercase(self, monkeypatch):
        """El flag es case-insensitive: FALSE también deshabilita."""
        monkeypatch.setenv("ENABLE_RESULT_PERSISTENCE", "FALSE")

        resultado = sc_module.get_client()

        assert resultado is None

    def test_get_client_enabled_missing_vars(self, monkeypatch):
        """
        Cuando ENABLE_RESULT_PERSISTENCE=true pero faltan SUPABASE_URL
        y SUPABASE_SERVICE_KEY → retorna None sin crash.
        """
        monkeypatch.setenv("ENABLE_RESULT_PERSISTENCE", "true")
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)

        resultado = sc_module.get_client()

        assert resultado is None


class TestSingleton:
    """Tests del patrón singleton de get_client().

    Nota de implementación: create_client se importa condicionalmente dentro
    del bloque try/except en supabase_client.py, por lo que NO es un atributo
    del módulo. La estrategia correcta para testearlo es:
      1. Parchear el módulo `supabase` directamente (supabase.create_client), O
      2. Inyectar el _client directamente en el módulo (más simple y robusto).
    Usamos la opción 2 para evitar dependencia del nombre de importación.
    """

    def test_get_client_enabled_success(self, monkeypatch, mocker):
        """
        Cuando ENABLE_RESULT_PERSISTENCE=true y variables presentes
        → retorna un Client (no None).

        Inyectamos create_client via importlib para parchear el símbolo
        correcto sin depender de si supabase-py está instalado.
        """
        monkeypatch.setenv("ENABLE_RESULT_PERSISTENCE", "true")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-service-key")

        mock_client = mocker.MagicMock()

        # Forzamos que el módulo use create_client mockeado:
        # dado que create_client se importa dentro del try, lo parcheamos
        # a nivel de módulo supabase si está disponible, o lo inyectamos
        # directamente en el namespace del módulo.
        mocker.patch.object(sc_module, "_SUPABASE_AVAILABLE", True)

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "supabase":
                fake = MagicMock()
                fake.create_client.return_value = mock_client
                return fake
            return original_import(name, *args, **kwargs)

        # Estrategia alternativa más simple: setattr directamente en el módulo
        # como si create_client ya hubiera sido importado.
        mock_create = mocker.MagicMock(return_value=mock_client)
        sc_module.create_client = mock_create  # type: ignore[attr-defined]

        resultado = sc_module.get_client()

        assert resultado is mock_client
        del sc_module.create_client  # limpieza

    def test_singleton_same_instance(self, monkeypatch, mocker):
        """
        Dos llamadas consecutivas a get_client() deben retornar
        exactamente el mismo objeto (identidad, no igualdad).
        """
        monkeypatch.setenv("ENABLE_RESULT_PERSISTENCE", "true")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-service-key")

        mock_client = mocker.MagicMock()
        mock_create = mocker.MagicMock(return_value=mock_client)
        mocker.patch.object(sc_module, "_SUPABASE_AVAILABLE", True)
        sc_module.create_client = mock_create  # type: ignore[attr-defined]

        primer_resultado = sc_module.get_client()
        segundo_resultado = sc_module.get_client()

        # Mismo objeto en memoria
        assert primer_resultado is segundo_resultado
        # create_client solo se llamó una vez (no dos)
        mock_create.assert_called_once()

        del sc_module.create_client  # limpieza

    def test_singleton_no_reconnect_after_first_success(self, monkeypatch, mocker):
        """
        Una vez que el singleton está inicializado, cambios en las
        variables de entorno no afectan: se reutiliza el cliente existente.
        """
        monkeypatch.setenv("ENABLE_RESULT_PERSISTENCE", "true")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-service-key")

        mock_client = mocker.MagicMock()
        mock_create = mocker.MagicMock(return_value=mock_client)
        mocker.patch.object(sc_module, "_SUPABASE_AVAILABLE", True)
        sc_module.create_client = mock_create  # type: ignore[attr-defined]

        # Primera llamada inicializa el singleton
        sc_module.get_client()

        # Segunda llamada con URL cambiada → igual retorna el singleton original
        monkeypatch.setenv("SUPABASE_URL", "https://otro.supabase.co")
        resultado = sc_module.get_client()

        assert resultado is mock_client

        del sc_module.create_client  # limpieza


class TestResolverDrogueriaIdUnica:
    """Tests para resolver_drogueria_id_unica() — cache en proceso del id de la
    droguería que sirve esta app, con DROGUERIA_ID como fuente determinística y
    fallback a SELECT...LIMIT 1 (sin filtro) si no está configurada."""

    def test_usa_droguria_id_de_env_sin_consultar_la_tabla(self, monkeypatch):
        """Regresión: si DROGUERIA_ID está seteada, NUNCA debe consultar
        droguerias — la variable de entorno es la única fuente de verdad, sin la
        ambigüedad de un LIMIT 1 no determinístico."""
        monkeypatch.setenv("DROGUERIA_ID", "drogueria-de-env")
        mock_client = MagicMock()

        resultado = sc_module.resolver_drogueria_id_unica(mock_client)

        assert resultado == "drogueria-de-env"
        mock_client.table.assert_not_called()

    def test_resuelve_y_cachea_via_fallback_sin_env(self, monkeypatch):
        monkeypatch.delenv("DROGUERIA_ID", raising=False)
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value.data = [
            {"id": "drogueria-123"}
        ]

        resultado = sc_module.resolver_drogueria_id_unica(mock_client)

        assert resultado == "drogueria-123"
        mock_client.table.assert_called_once_with("droguerias")

        # Segunda llamada: no vuelve a consultar (cache en proceso).
        mock_client.table.reset_mock()
        segundo = sc_module.resolver_drogueria_id_unica(mock_client)

        assert segundo == "drogueria-123"
        mock_client.table.assert_not_called()

    def test_sin_filas_retorna_none(self, monkeypatch):
        monkeypatch.delenv("DROGUERIA_ID", raising=False)
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value.data = []

        resultado = sc_module.resolver_drogueria_id_unica(mock_client)

        assert resultado is None

    def test_excepcion_retorna_none_sin_propagar(self, monkeypatch):
        monkeypatch.delenv("DROGUERIA_ID", raising=False)
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.side_effect = (
            RuntimeError("DB error simulado")
        )

        resultado = sc_module.resolver_drogueria_id_unica(mock_client)

        assert resultado is None

    def test_reset_client_for_testing_limpia_el_cache(self, monkeypatch):
        monkeypatch.delenv("DROGUERIA_ID", raising=False)
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value.data = [
            {"id": "drogueria-abc"}
        ]
        sc_module.resolver_drogueria_id_unica(mock_client)

        sc_module.reset_client_for_testing()
        mock_client.table.reset_mock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value.data = [
            {"id": "drogueria-xyz"}
        ]

        resultado = sc_module.resolver_drogueria_id_unica(mock_client)

        assert resultado == "drogueria-xyz"
        mock_client.table.assert_called_once_with("droguerias")
