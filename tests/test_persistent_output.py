"""
Tests para app/persistent_output.py — SHA256 + deduplicación + persistencia final.

Verifica:
- calcular_sha256: mismo archivo → mismo hash; archivos distintos → hashes distintos
- buscar_duplicado_con_lock: retorna UUID si hay duplicado, None si no hay
- persistir_output_final: crea extraction_result, valida rows vacío, warning en >50k rows
"""

import uuid
import tempfile
from pathlib import Path
from uuid import UUID
from unittest.mock import MagicMock

import pytest

import app.supabase_client as sc_module
from app import persistent_output


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Resetea el singleton de Supabase y el cache de drogueria_id antes de cada test."""
    sc_module.reset_client_for_testing()
    persistent_output._drogueria_id_cache = None
    yield
    sc_module.reset_client_for_testing()
    persistent_output._drogueria_id_cache = None


@pytest.fixture
def archivo_temp():
    """Crea un archivo temporal con contenido de prueba."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(b"contenido de prueba para hashing")
        return Path(f.name)


@pytest.fixture
def otro_archivo_temp():
    """Crea otro archivo temporal con contenido distinto."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(b"contenido completamente diferente")
        return Path(f.name)


@pytest.fixture
def mock_supabase_client(mocker):
    """
    Mock de supabase.Client para persistent_output.
    - table("droguerias").select(...).limit(...).execute() → una fila (resolución de
      drogueria_id, ver _resolver_drogueria_id).
    - cualquier otro table(...).insert(...).execute() → una fila con el id generado.
    """
    mock = MagicMock()
    extraction_uuid = str(uuid.uuid4())
    drogueria_uuid = str(uuid.uuid4())

    def _table(nombre):
        tabla_mock = MagicMock()
        if nombre == "droguerias":
            tabla_mock.select.return_value.limit.return_value.execute.return_value.data = [
                {"id": drogueria_uuid}
            ]
        else:
            tabla_mock.insert.return_value.execute.return_value.data = [{"id": extraction_uuid}]
        return tabla_mock

    mock.table.side_effect = _table
    mocker.patch("app.persistent_output.get_client", return_value=mock)
    return mock, extraction_uuid


# ---------------------------------------------------------------------------
# Tests de calcular_sha256
# ---------------------------------------------------------------------------

class TestCalcularSha256:
    """Tests para la función calcular_sha256()."""

    def test_calcular_sha256_same_file(self, archivo_temp):
        """El mismo archivo debe producir siempre el mismo hash."""
        hash1 = persistent_output.calcular_sha256(archivo_temp)
        hash2 = persistent_output.calcular_sha256(archivo_temp)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hexdigest tiene 64 caracteres

    def test_calcular_sha256_different_files(self, archivo_temp, otro_archivo_temp):
        """Archivos con distinto contenido deben producir hashes distintos."""
        hash1 = persistent_output.calcular_sha256(archivo_temp)
        hash2 = persistent_output.calcular_sha256(otro_archivo_temp)

        assert hash1 != hash2

    def test_calcular_sha256_file_not_found(self):
        """Si el archivo no existe → lanza excepción (FileNotFoundError)."""
        ruta_inexistente = Path("/ruta/que/no/existe/archivo.pdf")

        with pytest.raises((FileNotFoundError, OSError)):
            persistent_output.calcular_sha256(ruta_inexistente)


# ---------------------------------------------------------------------------
# Tests de buscar_duplicado_con_lock
# ---------------------------------------------------------------------------

class TestBuscarDuplicadoConLock:
    """Tests para buscar_duplicado_con_lock()."""

    @pytest.mark.asyncio
    async def test_buscar_duplicado_con_lock_found(self, mocker):
        """
        Si la RPC reserve_extraction retorna un UUID string →
        buscar_duplicado_con_lock retorna ese UUID.
        """
        existing_uuid = str(uuid.uuid4())
        mock = MagicMock()
        mock.rpc.return_value.execute.return_value.data = existing_uuid
        mocker.patch("app.persistent_output.get_client", return_value=mock)

        resultado = await persistent_output.buscar_duplicado_con_lock(
            source_sha256="a" * 64
        )

        assert resultado is not None
        assert isinstance(resultado, UUID)
        assert str(resultado) == existing_uuid

    @pytest.mark.asyncio
    async def test_buscar_duplicado_con_lock_not_found(self, mocker):
        """
        Si la RPC retorna None (sin duplicado) → buscar_duplicado_con_lock
        retorna None.
        """
        mock = MagicMock()
        mock.rpc.return_value.execute.return_value.data = None
        mocker.patch("app.persistent_output.get_client", return_value=mock)

        resultado = await persistent_output.buscar_duplicado_con_lock(
            source_sha256="b" * 64
        )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_buscar_duplicado_con_lock_client_none(self, mocker):
        """
        Cuando get_client() retorna None → retorna None sin crash.
        """
        mocker.patch("app.persistent_output.get_client", return_value=None)

        resultado = await persistent_output.buscar_duplicado_con_lock(
            source_sha256="c" * 64
        )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_buscar_duplicado_con_lock_exception_retorna_none(self, mocker):
        """
        Si la RPC lanza excepción → retorna None sin propagar
        (el sistema continúa sin verificación de duplicados).
        """
        mock = MagicMock()
        mock.rpc.return_value.execute.side_effect = RuntimeError("RPC error simulado")
        mocker.patch("app.persistent_output.get_client", return_value=mock)

        resultado = await persistent_output.buscar_duplicado_con_lock(
            source_sha256="d" * 64
        )

        assert resultado is None


# ---------------------------------------------------------------------------
# Tests de persistir_output_final
# ---------------------------------------------------------------------------

class TestPersistirOutputFinal:
    """Tests para persistir_output_final()."""

    @pytest.mark.asyncio
    async def test_persistir_output_final_success(self, mock_supabase_client, tmp_path):
        """
        persistir_output_final con datos válidos → crea extraction_result
        y retorna el UUID generado.
        """
        _, extraction_uuid = mock_supabase_client
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        resultado = await persistent_output.persistir_output_final(
            session_id=UUID("12345678-1234-5678-1234-567812345678"),
            doc_type="comparativa",
            rows=[{"proveedor": "ACME", "precio": "100"}],
            csv_path=csv_path,
            client_id="cliente_a",
            source_filename="comparativa.xlsx",
            source_sha256="e" * 64,
        )

        assert resultado is not None
        assert isinstance(resultado, UUID)
        assert str(resultado) == extraction_uuid

    @pytest.mark.asyncio
    async def test_persistir_output_final_empty_rows(self, mock_supabase_client, tmp_path):
        """
        rows vacío → retorna None (INSERT abortado, no se llama a Supabase).
        """
        mock, _ = mock_supabase_client
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        resultado = await persistent_output.persistir_output_final(
            session_id=UUID("12345678-1234-5678-1234-567812345678"),
            doc_type="comparativa",
            rows=[],
            csv_path=csv_path,
            client_id="cliente_a",
            source_filename="comparativa.xlsx",
            source_sha256="f" * 64,
        )

        assert resultado is None
        # No se debe haber llamado a table() en absoluto si rows está vacío
        # (la validación corta antes de resolver drogueria_id o insertar)
        mock.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_persistir_output_final_many_rows_warning(
        self, mock_supabase_client, tmp_path, caplog
    ):
        """
        Cuando rows > 50.000 → emite WARNING pero igual ejecuta el INSERT
        y retorna el UUID.
        """
        import logging
        _, extraction_uuid = mock_supabase_client
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        # Generamos 50.001 filas
        rows_grandes = [{"col": str(i)} for i in range(50_001)]

        with caplog.at_level(logging.WARNING, logger="app.persistent_output"):
            resultado = await persistent_output.persistir_output_final(
                session_id=UUID("12345678-1234-5678-1234-567812345678"),
                doc_type="comparativa",
                rows=rows_grandes,
                csv_path=csv_path,
                client_id="cliente_a",
                source_filename="grande.xlsx",
                source_sha256="g" * 64,
            )

        # El resultado sigue siendo válido (INSERT se ejecutó)
        assert resultado is not None
        # Debe haber un WARNING en los logs
        assert any("50" in msg for msg in caplog.messages), (
            "Se esperaba un WARNING sobre cantidad de filas"
        )

    @pytest.mark.asyncio
    async def test_persistir_output_final_client_none(self, mocker, tmp_path):
        """
        Cuando get_client() retorna None → retorna None sin crash.
        """
        mocker.patch("app.persistent_output.get_client", return_value=None)
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        resultado = await persistent_output.persistir_output_final(
            session_id=None,
            doc_type="comparativa",
            rows=[{"dato": "valor"}],
            csv_path=csv_path,
            client_id="cliente_b",
            source_filename="doc.pdf",
            source_sha256="h" * 64,
        )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_persistir_output_final_doc_type_invalido(
        self, mock_supabase_client, tmp_path
    ):
        """
        doc_type no reconocido → retorna None sin llamar a Supabase.
        """
        mock, _ = mock_supabase_client
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        resultado = await persistent_output.persistir_output_final(
            session_id=None,
            doc_type="tipo_invalido",
            rows=[{"dato": "valor"}],
            csv_path=csv_path,
            client_id="cliente_a",
            source_filename="doc.pdf",
            source_sha256="i" * 64,
        )

        assert resultado is None
