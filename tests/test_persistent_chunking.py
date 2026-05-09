"""
Tests para app/persistent_chunking.py — CRUD de sesiones y chunks.

Verifica:
- crear_sesion: retorna UUID válida o None según disponibilidad del client
- guardar_chunk: retorna True/False según éxito, y hace upsert idempotente
- cargar_chunks_existentes: retorna dict vacío o poblado
- cerrar_sesion: actualiza status sin propagar errores
"""

import uuid
from uuid import UUID
from unittest.mock import MagicMock

import pytest

import app.supabase_client as sc_module
from app import persistent_chunking


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Resetea el singleton de Supabase antes de cada test."""
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()


@pytest.fixture
def mock_supabase_client(mocker):
    """
    Mock de supabase.Client completo.

    Estructura del mock:
      client.table(nombre).insert(payload).execute() → MagicMock con .data
      client.table(nombre).upsert(...).execute()     → MagicMock
      client.table(nombre).select(...).eq(...).execute() → MagicMock con .data
      client.table(nombre).update(...).eq(...).execute() → MagicMock
    """
    mock = MagicMock()
    # Configuración por defecto para insert en processing_sessions
    session_uuid = str(uuid.uuid4())
    mock.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": session_uuid}
    ]
    # Patch del módulo para que get_client() retorne nuestro mock
    mocker.patch("app.persistent_chunking.get_client", return_value=mock)
    return mock, session_uuid


# ---------------------------------------------------------------------------
# Tests de crear_sesion
# ---------------------------------------------------------------------------

class TestCrearSesion:
    """Tests para la función crear_sesion()."""

    @pytest.mark.asyncio
    async def test_crear_sesion_success(self, mock_supabase_client):
        """
        crear_sesion con client disponible → retorna UUID válida que
        corresponde al id retornado por Supabase.
        """
        _, session_uuid = mock_supabase_client

        resultado = await persistent_chunking.crear_sesion(
            doc_name="comparativa_mayo.xlsx",
            client_id="cliente_a",
            total_chunks=5,
            doc_type="comparativa",
        )

        assert resultado is not None
        assert isinstance(resultado, UUID)
        assert str(resultado) == session_uuid

    @pytest.mark.asyncio
    async def test_crear_sesion_client_none(self, mocker):
        """
        Cuando get_client() retorna None → crear_sesion retorna None
        sin lanzar excepción (no crash).
        """
        mocker.patch("app.persistent_chunking.get_client", return_value=None)

        resultado = await persistent_chunking.crear_sesion(
            doc_name="documento.pdf",
            client_id="cliente_b",
            total_chunks=0,
            doc_type="licitacion",
        )

        assert resultado is None


# ---------------------------------------------------------------------------
# Tests de guardar_chunk
# ---------------------------------------------------------------------------

class TestGuardarChunk:
    """Tests para la función guardar_chunk()."""

    def test_guardar_chunk_success(self, mock_supabase_client):
        """
        guardar_chunk con client disponible → retorna True y
        verifica que se invocó upsert en 'chunk_results'.
        """
        mock, _ = mock_supabase_client
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.guardar_chunk(
            session_id=session_id,
            chunk_num=0,
            resultado_json={"proveedor": "ACME", "precio": 100.0},
        )

        assert resultado is True
        # Verificamos que se llamó a upsert en la tabla correcta
        mock.table.assert_called_with("chunk_results")
        mock.table.return_value.upsert.assert_called_once()

    def test_guardar_chunk_upsert_idempotente(self, mock_supabase_client):
        """
        Guardar el mismo chunk_num + session_id dos veces no debe
        lanzar error (upsert con ON CONFLICT es idempotente).
        """
        mock, _ = mock_supabase_client
        session_id = UUID("12345678-1234-5678-1234-567812345678")
        payload = {"proveedor": "ACME", "precio": 100.0}

        resultado_1 = persistent_chunking.guardar_chunk(
            session_id=session_id,
            chunk_num=1,
            resultado_json=payload,
        )
        resultado_2 = persistent_chunking.guardar_chunk(
            session_id=session_id,
            chunk_num=1,
            resultado_json=payload,
        )

        assert resultado_1 is True
        assert resultado_2 is True
        # Se llamó dos veces a upsert
        assert mock.table.return_value.upsert.call_count == 2

    def test_guardar_chunk_client_none(self, mocker):
        """
        Cuando get_client() retorna None → guardar_chunk retorna False
        sin lanzar excepción.
        """
        mocker.patch("app.persistent_chunking.get_client", return_value=None)
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.guardar_chunk(
            session_id=session_id,
            chunk_num=0,
            resultado_json={"dato": "valor"},
        )

        assert resultado is False

    def test_guardar_chunk_exception_retorna_false(self, mock_supabase_client):
        """
        Si la operación Supabase lanza una excepción → guardar_chunk
        la atrapa y retorna False (sin propagar).
        """
        mock, _ = mock_supabase_client
        mock.table.return_value.upsert.return_value.execute.side_effect = RuntimeError(
            "DB error simulado"
        )
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.guardar_chunk(
            session_id=session_id,
            chunk_num=2,
            resultado_json={"dato": "valor"},
        )

        assert resultado is False


# ---------------------------------------------------------------------------
# Tests de cargar_chunks_existentes
# ---------------------------------------------------------------------------

class TestCargarChunksExistentes:
    """Tests para cargar_chunks_existentes()."""

    def test_cargar_chunks_existentes_empty(self, mock_supabase_client):
        """
        Cuando la sesión no tiene chunks guardados → retorna dict vacío.
        """
        mock, _ = mock_supabase_client
        mock.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.cargar_chunks_existentes(session_id=session_id)

        assert resultado == {}

    def test_cargar_chunks_existentes_populated(self, mock_supabase_client):
        """
        Con chunks existentes → retorna {chunk_number: resultado_json}.
        """
        mock, _ = mock_supabase_client
        mock.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"chunk_number": 0, "resultado": {"proveedor": "ACME", "precio": 100.0}},
            {"chunk_number": 1, "resultado": {"proveedor": "XYZ", "precio": 200.0}},
        ]

        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.cargar_chunks_existentes(session_id=session_id)

        assert len(resultado) == 2
        assert resultado[0] == {"proveedor": "ACME", "precio": 100.0}
        assert resultado[1] == {"proveedor": "XYZ", "precio": 200.0}

    def test_cargar_chunks_existentes_client_none(self, mocker):
        """
        Cuando get_client() retorna None → retorna dict vacío sin crash.
        """
        mocker.patch("app.persistent_chunking.get_client", return_value=None)
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.cargar_chunks_existentes(session_id=session_id)

        assert resultado == {}


# ---------------------------------------------------------------------------
# Tests de cerrar_sesion
# ---------------------------------------------------------------------------

class TestCerrarSesion:
    """Tests para cerrar_sesion()."""

    @pytest.mark.asyncio
    async def test_cerrar_sesion_success(self, mock_supabase_client):
        """
        cerrar_sesion llama a update con status='completed' y
        no lanza excepción.
        """
        mock, _ = mock_supabase_client
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        # No debe lanzar excepción
        await persistent_chunking.cerrar_sesion(
            session_id=session_id,
            status="completed",
        )

        # Verificamos que se llamó a update en processing_sessions
        mock.table.assert_called_with("processing_sessions")
        mock.table.return_value.update.assert_called_once()
        # El payload de update debe incluir el status
        update_call_kwargs = mock.table.return_value.update.call_args[0][0]
        assert update_call_kwargs["status"] == "completed"

    @pytest.mark.asyncio
    async def test_cerrar_sesion_client_none(self, mocker):
        """
        Cuando get_client() retorna None → cerrar_sesion retorna
        silenciosamente sin crash.
        """
        mocker.patch("app.persistent_chunking.get_client", return_value=None)
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        # No debe lanzar excepción
        await persistent_chunking.cerrar_sesion(
            session_id=session_id,
            status="failed",
            error_msg="Error de prueba",
        )
