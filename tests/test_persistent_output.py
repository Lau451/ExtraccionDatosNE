"""
Tests para services/extraccion/persistent_output.py — SHA256 + deduplicación + persistencia final.

Verifica:
- calcular_sha256: mismo archivo → mismo hash; archivos distintos → hashes distintos
- buscar_duplicado_con_lock: retorna UUID si hay duplicado, None si no hay
- crear_extraction_processing: INSERT en 'processing' antes de correr el robot (T1)
- persistir_output_final: UPDATE por id a 'completed', valida rows vacío, warning en >50k rows
- marcar_extraccion_fallida: UPDATE por id a 'failed' + error_msg
- latido_extraccion: UPDATE de no-op que refresca updated_at de una fila 'processing' (T1d)
- marcar_processing_interrumpidos: sweep, 'processing' sin heartbeat reciente -> 'failed' (T1d)
"""

import uuid
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID
from unittest.mock import MagicMock

import pytest

# T1d: importado solo por su side-effect (`load_dotenv()` en el import del módulo) --
# persistent_output.get_client() lee SUPABASE_URL/SUPABASE_SERVICE_KEY directo de
# os.environ (sin dotenv propio), así que el test de integración de más abajo, que
# pega contra la DB real, necesita este import para correr aislado (sin depender de
# que algún otro módulo de test que sí importe services.extraccion.main haya cargado
# el .env antes, por orden de collection de pytest).
import services.extraccion.config  # noqa: F401
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
    async def test_crear_extraction_processing_incluye_subido_por_cuando_viene_usuario_id(
        self, mock_supabase_client
    ):
        """validar-extraccion-organizacion (T1) -- el uploader autenticado se
        persiste en extraction_results.subido_por (migración 0029), mismo
        criterio condicional que grupo_id/proceso_comercial_id (solo se
        incluye en el payload si vino)."""
        mock, _ = mock_supabase_client
        usuario_id = str(uuid.uuid4())

        await persistent_output.crear_extraction_processing(
            drogueria_id="drogueria-1",
            document_type="comparativa",
            source_filename="comparativa.xlsx",
            source_sha256="e" * 64,
            usuario_id=usuario_id,
        )

        payload = mock.table.return_value.insert.call_args[0][0]
        assert payload["subido_por"] == usuario_id

    @pytest.mark.asyncio
    async def test_crear_extraction_processing_sin_usuario_id_no_incluye_subido_por(
        self, mock_supabase_client
    ):
        mock, _ = mock_supabase_client

        await persistent_output.crear_extraction_processing(
            drogueria_id="drogueria-1",
            document_type="comparativa",
            source_filename="comparativa.xlsx",
            source_sha256="f" * 64,
        )

        payload = mock.table.return_value.insert.call_args[0][0]
        assert "subido_por" not in payload

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
# Tests de latido_extraccion (heartbeat, carga-asincrona T1d)
# ---------------------------------------------------------------------------

class TestLatidoExtraccion:
    """Tests para latido_extraccion(): el UPDATE de no-op que
    `_latir_periodicamente` (main.py) llama periódicamente mientras el robot
    corre, para que `marcar_processing_interrumpidos` nunca confunda un job
    vivo con uno huérfano (el trigger t_u_er refresca `updated_at` en
    cualquier UPDATE, sin que haga falta cambiar ninguna otra columna)."""

    @pytest.mark.asyncio
    async def test_latido_actualiza_filtrando_por_id_drogueria_y_status_processing(self, mocker):
        mock = MagicMock()
        tabla_mock = MagicMock()
        (
            tabla_mock.update.return_value.eq.return_value.eq.return_value.eq.return_value
            .execute.return_value.data
        ) = [{"id": "extraction-1"}]
        mock.table.return_value = tabla_mock
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        extraction_id = uuid.uuid4()
        await persistent_output.latido_extraccion(
            extraction_id=extraction_id, drogueria_id="drogueria-1"
        )

        payload = tabla_mock.update.call_args[0][0]
        assert payload["status"] == "processing"
        tabla_mock.update.return_value.eq.assert_any_call("id", str(extraction_id))
        tabla_mock.update.return_value.eq.return_value.eq.assert_any_call(
            "drogueria_id", "drogueria-1"
        )
        # El tercer .eq("status", "processing") es lo que evita "resucitar" una
        # fila que ya terminó (completed/failed) en un tick anterior al cancel.
        tabla_mock.update.return_value.eq.return_value.eq.return_value.eq.assert_any_call(
            "status", "processing"
        )

    @pytest.mark.asyncio
    async def test_latido_client_none_no_crashea(self, mocker):
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=None)

        # No debe lanzar excepción
        await persistent_output.latido_extraccion(
            extraction_id=uuid.uuid4(), drogueria_id="drogueria-1"
        )

    @pytest.mark.asyncio
    async def test_latido_excepcion_no_propaga(self, mocker):
        mock = MagicMock()
        mock.table.side_effect = RuntimeError("Supabase caído")
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        # No debe lanzar excepción
        await persistent_output.latido_extraccion(
            extraction_id=uuid.uuid4(), drogueria_id="drogueria-1"
        )


# ---------------------------------------------------------------------------
# Tests de marcar_processing_interrumpidos (sweep, carga-asincrona T1/T1d)
# ---------------------------------------------------------------------------

class TestMarcarProcessingInterrumpidos:
    """Tests para marcar_processing_interrumpidos().

    T1d (carga-asincrona): filtra por `updated_at` (`.lt("updated_at", cutoff)`), no
    por `created_at` como en T1c -- un job vivo llama a `latido_extraccion` cada
    `_LATIDO_INTERVALO_SEGUNDOS` (main.py) y ese UPDATE mantiene `updated_at` fresco
    mientras corre, sin importar cuánto tarde el robot o cuánto encole el
    `_GEMINI_SEMAPHORE`. Eso permite un umbral corto (ver
    `_SWEEP_EDAD_MINIMA_SEGUNDOS_DEFAULT`, ~5x el intervalo del heartbeat) en vez del
    umbral de 60 min dimensionado sobre el peor caso de Gemini/semaphore que usaba
    T1c -- y sigue siendo seguro con un segundo proceso compartiendo la misma base
    (ej. un server local de desarrollo), porque un robot legítimamente en curso en
    ese otro proceso sigue latiendo su propia fila. Este mismo sweep corre al
    arrancar Y periódicamente (`_sweep_periodico` en main.py) para no depender solo
    del arranque del proceso."""

    @pytest.mark.asyncio
    async def test_marca_failed_las_filas_processing_mas_viejas_que_el_umbral(self, mocker):
        mock = MagicMock()
        tabla_mock = MagicMock()
        tabla_mock.update.return_value.eq.return_value.lt.return_value.execute.return_value.data = [
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
    async def test_sweep_filtra_por_antiguedad_de_updated_at_con_el_umbral_default(self, mocker):
        """T1d: la query agrega `.lt("updated_at", cutoff)`, no `.lt("created_at", ...)`
        (T1c) -- una fila 'processing' cuyo `updated_at` es más reciente que el umbral
        default (porque su heartbeat la sigue refrescando) nunca llega a este mock (se
        filtra del lado del servidor), así que solo se verifica que la query pida ese
        filtro sobre `updated_at` con un cutoff coherente con el umbral default."""
        mock = MagicMock()
        tabla_mock = MagicMock()
        tabla_mock.update.return_value.eq.return_value.lt.return_value.execute.return_value.data = [
            {"id": str(uuid.uuid4())},
        ]
        mock.table.return_value = tabla_mock
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        antes = datetime.now(timezone.utc)
        afectadas = await persistent_output.marcar_processing_interrumpidos()
        despues = datetime.now(timezone.utc)

        assert afectadas == 1
        campo, cutoff_iso = tabla_mock.update.return_value.eq.return_value.lt.call_args[0]
        assert campo == "updated_at"
        cutoff = datetime.fromisoformat(cutoff_iso)
        umbral = timedelta(seconds=persistent_output._SWEEP_EDAD_MINIMA_SEGUNDOS_DEFAULT)
        assert antes - umbral <= cutoff <= despues - umbral

    @pytest.mark.asyncio
    async def test_sweep_acepta_un_umbral_de_antiguedad_custom(self, mocker):
        """El parámetro `edad_minima_segundos` permite testear el filtro con un umbral
        corto sin esperar minutos reales -- hoy ni `_sweep_periodico` ni el sweep de
        arranque (lifespan) en main.py lo usan: ambos llaman esta función sin
        argumentos y dependen siempre de `_SWEEP_EDAD_MINIMA_SEGUNDOS_DEFAULT`."""
        mock = MagicMock()
        tabla_mock = MagicMock()
        tabla_mock.update.return_value.eq.return_value.lt.return_value.execute.return_value.data = []
        mock.table.return_value = tabla_mock
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock)

        antes = datetime.now(timezone.utc)
        await persistent_output.marcar_processing_interrumpidos(edad_minima_segundos=120)
        despues = datetime.now(timezone.utc)

        _, cutoff_iso = tabla_mock.update.return_value.eq.return_value.lt.call_args[0]
        cutoff = datetime.fromisoformat(cutoff_iso)
        assert antes - timedelta(seconds=120) <= cutoff <= despues - timedelta(seconds=120)

    @pytest.mark.asyncio
    async def test_sin_filas_processing_retorna_cero(self, mocker):
        mock = MagicMock()
        tabla_mock = MagicMock()
        tabla_mock.update.return_value.eq.return_value.lt.return_value.execute.return_value.data = []
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


@pytest.mark.integration
async def test_sweep_contra_la_rest_real_falla_solo_la_fila_con_updated_at_viejo(
    service_client, seed_drogueria
):
    """T1d: contra la REST real (no mockeada, a diferencia de toda la clase de
    arriba) -- el review de T1c señaló que un cutoff isoformat con offset
    '+00:00' (`datetime.isoformat()` en UTC) podría no percent-encodearse bien
    en la URL que arma PostgREST/postgrest-py, rompiendo `.lt(...)` en
    silencio (ej. si el '+' llega literal, PostgREST podría leerlo como un
    espacio y fallar el parseo del timestamp). Este test ejercita esa query
    contra la base real: una fila 'processing' con `updated_at` viejo (el
    trigger t_u_er solo pisa `updated_at` en UPDATE, nunca en INSERT -- por
    eso se puede setear un valor viejo directo en el INSERT) debe terminar
    'failed', y una fila 'processing' fresca (heartbeat reciente, en la
    práctica) debe quedar intacta."""
    import secrets

    sha_vieja = secrets.token_hex(32)
    sha_fresca = secrets.token_hex(32)
    hace_dos_horas = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    huerfana = (
        service_client.table("extraction_results")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "document_type": "licitacion",
                "source_filename": "huerfana.pdf",
                "source_sha256": sha_vieja,
                "row_count": 0,
                "status": "processing",
                "updated_at": hace_dos_horas,
            }
        )
        .execute()
        .data[0]
    )
    en_vuelo = (
        service_client.table("extraction_results")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "document_type": "licitacion",
                "source_filename": "en-vuelo.pdf",
                "source_sha256": sha_fresca,
                "row_count": 0,
                "status": "processing",
            }
        )
        .execute()
        .data[0]
    )

    try:
        # El sweep es global y la base TEST es compartida: con un umbral de 30
        # min solo toca filas sin latido hace media hora (huérfanas de verdad,
        # que el sweep real ya fallaría a los 5 min), nunca un job vivo de otro
        # proceso (late cada 60s). La "huérfana" (2 horas) queda muy por encima.
        afectadas = await persistent_output.marcar_processing_interrumpidos(
            edad_minima_segundos=30 * 60
        )

        assert afectadas >= 1

        estado_huerfana = (
            service_client.table("extraction_results")
            .select("status")
            .eq("id", huerfana["id"])
            .execute()
            .data
        )
        assert estado_huerfana == [{"status": "failed"}]

        estado_en_vuelo = (
            service_client.table("extraction_results")
            .select("status")
            .eq("id", en_vuelo["id"])
            .execute()
            .data
        )
        assert estado_en_vuelo == [{"status": "processing"}]
    finally:
        service_client.table("extraction_results").delete().eq("id", huerfana["id"]).execute()
        service_client.table("extraction_results").delete().eq("id", en_vuelo["id"]).execute()
