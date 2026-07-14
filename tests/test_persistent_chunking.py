"""
Tests para services/extraccion/persistent_chunking.py — CRUD de sesiones y chunks.

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

import services.extraccion.supabase_client as sc_module
from services.extraccion import persistent_chunking


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

    "droguerias" se distingue del resto vía side_effect (igual que en
    test_persistent_output.py) para que resolver_drogueria_id_unica() reciba una
    respuesta determinística en vez de la permisividad de un MagicMock genérico
    (que sería truthy/subscriptable igual, ocultando el bug que estamos probando).

    Estructura del mock:
      client.table("droguerias").select(...).limit(...).execute() → una fila real
      client.table(nombre).insert(payload).execute() → MagicMock con .data (resto de tablas)
      client.table(nombre).upsert(...).execute()     → MagicMock
      client.table(nombre).select(...).eq(...).execute() → MagicMock con .data
      client.table(nombre).update(...).eq(...).execute() → MagicMock
    """
    mock = MagicMock()
    session_uuid = str(uuid.uuid4())
    drogueria_uuid = str(uuid.uuid4())
    tablas: dict[str, MagicMock] = {}

    def _table(nombre):
        if nombre not in tablas:
            tabla_mock = MagicMock()
            if nombre == "droguerias":
                tabla_mock.select.return_value.limit.return_value.execute.return_value.data = [
                    {"id": drogueria_uuid}
                ]
            else:
                tabla_mock.insert.return_value.execute.return_value.data = [{"id": session_uuid}]
            tablas[nombre] = tabla_mock
        return tablas[nombre]

    mock.table.side_effect = _table
    # Patch del módulo para que get_client() retorne nuestro mock
    mocker.patch("services.extraccion.persistent_chunking.get_client", return_value=mock)
    return mock, session_uuid, tablas


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
        _, session_uuid, _tablas = mock_supabase_client

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
        mocker.patch("services.extraccion.persistent_chunking.get_client", return_value=None)

        resultado = await persistent_chunking.crear_sesion(
            doc_name="documento.pdf",
            client_id="cliente_b",
            total_chunks=0,
            doc_type="licitacion",
        )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_crear_sesion_payload_no_incluye_client_id_e_incluye_drogueria_id(
        self, mock_supabase_client
    ):
        """
        Regresión: processing_sessions no tiene columna client_id (schema nuevo de
        presupuestacion/) y sí exige drogueria_id NOT NULL. El INSERT real a
        processing_sessions no debe mandar "client_id" y SÍ debe mandar
        "drogueria_id" con el valor resuelto por resolver_drogueria_id_unica().
        """
        mock, _, _tablas = mock_supabase_client

        await persistent_chunking.crear_sesion(
            doc_name="comparativa_mayo.xlsx",
            client_id="cliente_a",
            total_chunks=5,
            doc_type="comparativa",
            formato_usado_id="formato-1",
        )

        payload = _tablas["processing_sessions"].insert.call_args[0][0]
        assert "client_id" not in payload
        assert "drogueria_id" in payload and payload["drogueria_id"] is not None
        assert payload["formato_usado_id"] == "formato-1"


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
        mock, _, _tablas = mock_supabase_client
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.guardar_chunk(
            session_id=session_id,
            chunk_num=0,
            resultado_json={"proveedor": "ACME", "precio": 100.0},
        )

        assert resultado is True
        # Verificamos que se llamó a upsert en la tabla correcta
        mock.table.assert_called_with("chunk_results")
        _tablas["chunk_results"].upsert.assert_called_once()

    def test_guardar_chunk_upsert_idempotente(self, mock_supabase_client):
        """
        Guardar el mismo chunk_num + session_id dos veces no debe
        lanzar error (upsert con ON CONFLICT es idempotente).
        """
        mock, _, _tablas = mock_supabase_client
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
        assert _tablas["chunk_results"].upsert.call_count == 2

    def test_guardar_chunk_client_none(self, mocker):
        """
        Cuando get_client() retorna None → guardar_chunk retorna False
        sin lanzar excepción.
        """
        mocker.patch("services.extraccion.persistent_chunking.get_client", return_value=None)
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.guardar_chunk(
            session_id=session_id,
            chunk_num=0,
            resultado_json={"dato": "valor"},
        )

        assert resultado is False

    def test_guardar_chunk_payload_incluye_drogueria_id(self, mock_supabase_client):
        """
        Regresión: chunk_results también exige drogueria_id NOT NULL. El upsert real
        debe incluirlo (resuelto por resolver_drogueria_id_unica()).
        """
        mock, _, _tablas = mock_supabase_client
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        persistent_chunking.guardar_chunk(
            session_id=session_id,
            chunk_num=0,
            resultado_json={"proveedor": "ACME", "precio": 100.0},
        )

        payload = _tablas["chunk_results"].upsert.call_args[0][0]
        assert "drogueria_id" in payload and payload["drogueria_id"] is not None

    def test_guardar_chunk_exception_retorna_false(self, mock_supabase_client):
        """
        Si la operación Supabase lanza una excepción → guardar_chunk
        la atrapa y retorna False (sin propagar).
        """
        mock, _, _tablas = mock_supabase_client
        # Pre-poblamos la entrada de "chunk_results" en el mock (side_effect la crea
        # perezosamente) para poder configurar el error ANTES de que guardar_chunk
        # la llame de verdad.
        mock.table("chunk_results").upsert.return_value.execute.side_effect = RuntimeError(
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
        mock, _, _tablas = mock_supabase_client
        mock.table("chunk_results").select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

        session_id = UUID("12345678-1234-5678-1234-567812345678")

        resultado = persistent_chunking.cargar_chunks_existentes(session_id=session_id)

        assert resultado == {}

    def test_cargar_chunks_existentes_populated(self, mock_supabase_client):
        """
        Con chunks existentes → retorna {chunk_number: resultado_json}.
        """
        mock, _, _tablas = mock_supabase_client
        mock.table("chunk_results").select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
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
        mocker.patch("services.extraccion.persistent_chunking.get_client", return_value=None)
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
        mock, _, _tablas = mock_supabase_client
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        # No debe lanzar excepción
        await persistent_chunking.cerrar_sesion(
            session_id=session_id,
            status="completed",
        )

        # Verificamos que se llamó a update en processing_sessions
        mock.table.assert_called_with("processing_sessions")
        _tablas["processing_sessions"].update.assert_called_once()
        # El payload de update debe incluir el status
        update_call_kwargs = _tablas["processing_sessions"].update.call_args[0][0]
        assert update_call_kwargs["status"] == "completed"

    @pytest.mark.asyncio
    async def test_cerrar_sesion_client_none(self, mocker):
        """
        Cuando get_client() retorna None → cerrar_sesion retorna
        silenciosamente sin crash.
        """
        mocker.patch("services.extraccion.persistent_chunking.get_client", return_value=None)
        session_id = UUID("12345678-1234-5678-1234-567812345678")

        # No debe lanzar excepción
        await persistent_chunking.cerrar_sesion(
            session_id=session_id,
            status="failed",
            error_msg="Error de prueba",
        )
