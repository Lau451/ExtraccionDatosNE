"""
Tests para services/extraccion/persistent_output.py — SHA256 + deduplicación + persistencia final.

Verifica:
- calcular_sha256: mismo archivo → mismo hash; archivos distintos → hashes distintos
- buscar_duplicado_con_lock: retorna UUID si hay duplicado, None si no hay
- crear_extraction_processing: INSERT en 'processing' antes de correr el robot (T1)
- persistir_output_final: UPDATE por id a 'completed', valida rows vacío, warning en >50k rows
- marcar_extraccion_fallida: UPDATE por id a 'failed' + error_msg
- marcar_processing_interrumpidos: sweep de arranque, 'processing' viejos -> 'failed'
"""

import uuid
import tempfile
from pathlib import Path
from uuid import UUID
from unittest.mock import MagicMock

import pytest

import services.extraccion.supabase_client as sc_module
from services.extraccion import persistent_output


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Resetea el singleton de Supabase y el cache de drogueria_id (compartido en
    app.supabase_client) antes de cada test."""
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()


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
    Mock de supabase.Client para persistent_output. drogueria_id ya no se resuelve
    acá -- lo enhebra explícito el caller. table(...).insert(...).execute() → una
    fila con el id generado. Un solo table("extraction_results") por invocación
    -- mock.table.return_value referencia directamente ese mismo mock (sin
    side_effect: no hace falta despachar por nombre de tabla acá), así los
    tests pueden assertear sobre mock.table.return_value.insert.call_args.
    """
    mock = MagicMock()
    extraction_uuid = str(uuid.uuid4())
    mock.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": extraction_uuid}
    ]
    mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)
    return mock, extraction_uuid


@pytest.fixture
def mock_supabase_client_update(mocker):
    """
    Variante de mock_supabase_client para las funciones que hacen UPDATE por id
    (persistir_output_final / marcar_extraccion_fallida, desde carga-asincrona T1):
    table(...).update(...).eq(...).eq(...).execute() → una fila afectada.
    """
    mock = MagicMock()
    extraction_uuid = str(uuid.uuid4())
    mock.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": extraction_uuid}
    ]
    mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)
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
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        resultado = await persistent_output.buscar_duplicado_con_lock(
            source_sha256="a" * 64, drogueria_id="drogueria-1"
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
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        resultado = await persistent_output.buscar_duplicado_con_lock(
            source_sha256="b" * 64, drogueria_id="drogueria-1"
        )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_buscar_duplicado_con_lock_client_none(self, mocker):
        """
        Cuando get_client() retorna None → retorna None sin crash.
        """
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=None)

        resultado = await persistent_output.buscar_duplicado_con_lock(
            source_sha256="c" * 64, drogueria_id="drogueria-1"
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
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        resultado = await persistent_output.buscar_duplicado_con_lock(
            source_sha256="d" * 64, drogueria_id="drogueria-1"
        )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_buscar_duplicado_con_lock_exception_logea_error_explicito(self, mocker, caplog):
        """
        Si la RPC reserve_extraction lanza excepción (ej: firma desactualizada
        porque falta la migración 0027), el fallo debe quedar en el log a
        nivel ERROR con un mensaje explícito de que la deduplicación quedó
        DESHABILITADA — un WARNING silencioso esconde que el sistema dejó de
        detectar duplicados entre tenants.
        """
        import logging

        mock = MagicMock()
        mock.rpc.return_value.execute.side_effect = RuntimeError("RPC error simulado")
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        with caplog.at_level(logging.ERROR, logger="services.extraccion.persistent_output"):
            resultado = await persistent_output.buscar_duplicado_con_lock(
                source_sha256="d" * 64, drogueria_id="drogueria-1"
            )

        assert resultado is None
        errores = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errores, f"Se esperaba un log ERROR. Registros: {caplog.records}"
        assert any("DESHABILITADA" in r.message or "deshabilitada" in r.message.lower() for r in errores)
        assert any("0027" in r.message for r in errores)


# ---------------------------------------------------------------------------
# Tests de crear_extraction_processing (carga-asincrona, T1)
# ---------------------------------------------------------------------------

class TestCrearExtractionProcessing:
    """Tests para crear_extraction_processing()."""

    @pytest.mark.asyncio
    async def test_crear_extraction_processing_success(self, mock_supabase_client):
        mock, extraction_uuid = mock_supabase_client

        resultado = await persistent_output.crear_extraction_processing(
            drogueria_id="drogueria-1",
            document_type="comparativa",
            source_filename="comparativa.xlsx",
            source_sha256="a" * 64,
        )

        assert resultado is not None
        assert isinstance(resultado, UUID)
        assert str(resultado) == extraction_uuid

        payload = mock.table.return_value.insert.call_args[0][0]
        assert payload["status"] == "processing"
        assert payload["row_count"] == 0
        assert "grupo_id" not in payload
        assert "proceso_comercial_id" not in payload

    @pytest.mark.asyncio
    async def test_crear_extraction_processing_incluye_grupo_id_y_proceso_comercial_id(
        self, mock_supabase_client
    ):
        mock, _ = mock_supabase_client
        grupo_id = str(uuid.uuid4())
        proceso_id = str(uuid.uuid4())

        await persistent_output.crear_extraction_processing(
            drogueria_id="drogueria-1",
            document_type="orden_compra",
            source_filename="orden.pdf",
            source_sha256="b" * 64,
            grupo_id=grupo_id,
            proceso_comercial_id=proceso_id,
        )

        payload = mock.table.return_value.insert.call_args[0][0]
        assert payload["grupo_id"] == grupo_id
        assert payload["proceso_comercial_id"] == proceso_id

    @pytest.mark.asyncio
    async def test_crear_extraction_processing_client_none(self, mocker):
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=None)

        resultado = await persistent_output.crear_extraction_processing(
            drogueria_id="drogueria-1",
            document_type="comparativa",
            source_filename="doc.pdf",
            source_sha256="c" * 64,
        )

        assert resultado is None


# ---------------------------------------------------------------------------
# Tests de persistir_output_final (UPDATE por id desde la migración 0028)
# ---------------------------------------------------------------------------

class TestPersistirOutputFinal:
    """Tests para persistir_output_final()."""

    @pytest.mark.asyncio
    async def test_persistir_output_final_success(self, mock_supabase_client_update, tmp_path):
        """
        persistir_output_final con datos válidos → actualiza la fila 'processing'
        ya existente (crear_extraction_processing) a 'completed' y retorna el
        mismo extraction_id recibido.
        """
        _, extraction_uuid = mock_supabase_client_update
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        resultado = await persistent_output.persistir_output_final(
            extraction_id=UUID(extraction_uuid),
            session_id=UUID("12345678-1234-5678-1234-567812345678"),
            doc_type="comparativa",
            rows=[{"proveedor": "ACME", "precio": "100"}],
            csv_path=csv_path,
            client_id="cliente_a",
            source_filename="comparativa.xlsx",
            source_sha256="e" * 64,
            drogueria_id="drogueria-1",
        )

        assert resultado is not None
        assert isinstance(resultado, UUID)
        assert str(resultado) == extraction_uuid

    @pytest.mark.asyncio
    async def test_persistir_output_final_empty_rows(self, mock_supabase_client_update, tmp_path):
        """
        rows vacío → retorna None (UPDATE abortado, no se llama a Supabase).
        """
        mock, extraction_uuid = mock_supabase_client_update
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        resultado = await persistent_output.persistir_output_final(
            extraction_id=UUID(extraction_uuid),
            session_id=UUID("12345678-1234-5678-1234-567812345678"),
            doc_type="comparativa",
            rows=[],
            csv_path=csv_path,
            client_id="cliente_a",
            source_filename="comparativa.xlsx",
            source_sha256="f" * 64,
            drogueria_id="drogueria-1",
        )

        assert resultado is None
        # No se debe haber llamado a table() en absoluto si rows está vacío
        # (la validación corta antes de resolver drogueria_id o actualizar)
        mock.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_persistir_output_final_many_rows_warning(
        self, mock_supabase_client_update, tmp_path, caplog
    ):
        """
        Cuando rows > 50.000 → emite WARNING pero igual ejecuta el UPDATE
        y retorna el extraction_id.
        """
        import logging
        _, extraction_uuid = mock_supabase_client_update
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        # Generamos 50.001 filas
        rows_grandes = [{"col": str(i)} for i in range(50_001)]

        with caplog.at_level(logging.WARNING, logger="services.extraccion.persistent_output"):
            resultado = await persistent_output.persistir_output_final(
                extraction_id=UUID(extraction_uuid),
                session_id=UUID("12345678-1234-5678-1234-567812345678"),
                doc_type="comparativa",
                rows=rows_grandes,
                csv_path=csv_path,
                client_id="cliente_a",
                source_filename="grande.xlsx",
                source_sha256="g" * 64,
                drogueria_id="drogueria-1",
            )

        # El resultado sigue siendo válido (UPDATE se ejecutó)
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
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=None)
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        resultado = await persistent_output.persistir_output_final(
            extraction_id=uuid.uuid4(),
            session_id=None,
            doc_type="comparativa",
            rows=[{"dato": "valor"}],
            csv_path=csv_path,
            client_id="cliente_b",
            source_filename="doc.pdf",
            source_sha256="h" * 64,
            drogueria_id="drogueria-1",
        )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_persistir_output_final_doc_type_invalido(
        self, mock_supabase_client_update, tmp_path
    ):
        """
        doc_type no reconocido → retorna None sin llamar a Supabase.
        """
        mock, extraction_uuid = mock_supabase_client_update
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        resultado = await persistent_output.persistir_output_final(
            extraction_id=UUID(extraction_uuid),
            session_id=None,
            doc_type="tipo_invalido",
            rows=[{"dato": "valor"}],
            csv_path=csv_path,
            client_id="cliente_a",
            source_filename="doc.pdf",
            source_sha256="i" * 64,
            drogueria_id="drogueria-1",
        )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_persistir_output_final_update_filtra_por_extraction_id_y_drogueria(
        self, mock_supabase_client_update, tmp_path
    ):
        """El UPDATE debe filtrar por id Y drogueria_id -- nunca debe poder
        actualizar (ni mucho menos "completar") la fila de otra droguería."""
        mock, extraction_uuid = mock_supabase_client_update
        csv_path = tmp_path / "resultado.csv"
        csv_path.touch()

        await persistent_output.persistir_output_final(
            extraction_id=UUID(extraction_uuid),
            session_id=None,
            doc_type="comparativa",
            rows=[{"dato": "valor"}],
            csv_path=csv_path,
            client_id="cliente_a",
            source_filename="doc.pdf",
            source_sha256="j" * 64,
            drogueria_id="drogueria-1",
        )

        tabla = mock.table.return_value
        tabla.update.assert_called_once()
        payload = tabla.update.call_args[0][0]
        assert payload["status"] == "completed"
        tabla.update.return_value.eq.assert_any_call("id", extraction_uuid)
        tabla.update.return_value.eq.return_value.eq.assert_any_call("drogueria_id", "drogueria-1")


# ---------------------------------------------------------------------------
# Tests de marcar_extraccion_fallida (carga-asincrona, T1)
# ---------------------------------------------------------------------------

class TestMarcarExtraccionFallida:
    """Tests para marcar_extraccion_fallida()."""

    @pytest.mark.asyncio
    async def test_marcar_extraccion_fallida_actualiza_status_y_error_msg(
        self, mock_supabase_client_update
    ):
        mock, extraction_uuid = mock_supabase_client_update

        await persistent_output.marcar_extraccion_fallida(
            extraction_id=UUID(extraction_uuid),
            drogueria_id="drogueria-1",
            error_msg="No se detectaron proveedores en el documento",
        )

        payload = mock.table.return_value.update.call_args[0][0]
        assert payload["status"] == "failed"
        assert payload["error_msg"] == "No se detectaron proveedores en el documento"

    @pytest.mark.asyncio
    async def test_marcar_extraccion_fallida_extraction_id_none_no_llama_a_supabase(
        self, mock_supabase_client_update
    ):
        """extraction_id=None (persistencia no disponible al crear la fila) es un
        no-op -- no hay fila que actualizar."""
        mock, _ = mock_supabase_client_update

        await persistent_output.marcar_extraccion_fallida(
            extraction_id=None,
            drogueria_id="drogueria-1",
            error_msg="Error interno del servidor",
        )

        mock.table.assert_not_called()

    @pytest.mark.asyncio
    async def test_marcar_extraccion_fallida_client_none_no_crashea(self, mocker):
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=None)

        # No debe lanzar excepción
        await persistent_output.marcar_extraccion_fallida(
            extraction_id=uuid.uuid4(),
            drogueria_id="drogueria-1",
            error_msg="Error interno del servidor",
        )

    @pytest.mark.asyncio
    async def test_marcar_extraccion_fallida_excepcion_no_propaga(self, mocker):
        mock = MagicMock()
        mock.table.side_effect = RuntimeError("Supabase caído")
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        # No debe lanzar excepción
        await persistent_output.marcar_extraccion_fallida(
            extraction_id=uuid.uuid4(),
            drogueria_id="drogueria-1",
            error_msg="Error interno del servidor",
        )


# ---------------------------------------------------------------------------
# Tests de marcar_processing_interrumpidos (sweep de arranque, carga-asincrona T1)
# ---------------------------------------------------------------------------

class TestMarcarProcessingInterrumpidos:
    """Tests para marcar_processing_interrumpidos().

    T1b (carga-asincrona): el sweep de arranque barre TODAS las filas 'processing',
    sin filtrar por antigüedad -- docker-compose.yml define una sola instancia por
    servicio (container_name fijo, sin deploy.replicas) y el Dockerfile arranca
    uvicorn sin --workers, así que un solo proceso corre alguna vez los background
    tasks. Cuando el lifespan de este proceso arranca, el proceso anterior (si lo
    hubo) ya terminó por completo -- ningún robot sigue vivo -- así que CUALQUIER
    fila 'processing' encontrada acá es huérfana, sin importar cuán reciente sea.
    Antes de esta tarea, un umbral de antigüedad (10 min) dejaba huérfanas para
    siempre las filas más jóvenes que el umbral (el bug que motivó T1b)."""

    @pytest.mark.asyncio
    async def test_marca_failed_las_filas_processing_devueltas(self, mocker):
        mock = MagicMock()
        tabla_mock = MagicMock()
        tabla_mock.update.return_value.eq.return_value.execute.return_value.data = [
            {"id": str(uuid.uuid4())},
            {"id": str(uuid.uuid4())},
        ]
        mock.table.return_value = tabla_mock
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        afectadas = await persistent_output.marcar_processing_interrumpidos()

        assert afectadas == 2
        payload = tabla_mock.update.call_args[0][0]
        assert payload["status"] == "failed"
        assert "Procesamiento interrumpido" in payload["error_msg"]
        tabla_mock.update.return_value.eq.assert_any_call("status", "processing")

    @pytest.mark.asyncio
    async def test_sweep_no_filtra_por_antiguedad(self, mocker):
        """El bug de T1b: una fila 'processing' recién creada (segundos de
        antigüedad) también debe barrerse -- no hay ningún `.lt("created_at", ...)`
        en la query, porque en esta topología (una sola instancia, sin --workers)
        el proceso que la creó ya no existe cuando el sweep corre."""
        mock = MagicMock()
        tabla_mock = MagicMock()
        tabla_mock.update.return_value.eq.return_value.execute.return_value.data = [
            {"id": str(uuid.uuid4())},
        ]
        mock.table.return_value = tabla_mock
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        afectadas = await persistent_output.marcar_processing_interrumpidos()

        assert afectadas == 1
        # La cadena de la query es SOLO update().eq("status", "processing").execute() --
        # ningún método .lt(...) se invoca (sin filtro de antigüedad).
        tabla_mock.update.return_value.eq.return_value.lt.assert_not_called()

    @pytest.mark.asyncio
    async def test_sin_filas_processing_retorna_cero(self, mocker):
        mock = MagicMock()
        tabla_mock = MagicMock()
        tabla_mock.update.return_value.eq.return_value.execute.return_value.data = []
        mock.table.return_value = tabla_mock
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        afectadas = await persistent_output.marcar_processing_interrumpidos()

        assert afectadas == 0

    @pytest.mark.asyncio
    async def test_client_none_retorna_cero_sin_crash(self, mocker):
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=None)

        afectadas = await persistent_output.marcar_processing_interrumpidos()

        assert afectadas == 0

    @pytest.mark.asyncio
    async def test_excepcion_no_propaga_y_retorna_cero(self, mocker):
        mock = MagicMock()
        mock.table.side_effect = RuntimeError("Supabase caído")
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        # No debe lanzar excepción
        afectadas = await persistent_output.marcar_processing_interrumpidos()

        assert afectadas == 0
