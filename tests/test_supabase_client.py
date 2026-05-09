"""
Tests para app/supabase_client.py — Feature flag + singleton.

Verifica:
- ENABLE_RESULT_PERSISTENCE=false → retorna None
- Variables faltantes → retorna None sin crash
- Variables presentes → retorna Client singleton
- Dos llamadas → mismo objeto (singleton pattern)
"""

import pytest
from unittest.mock import MagicMock
import app.supabase_client as sc_module


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
