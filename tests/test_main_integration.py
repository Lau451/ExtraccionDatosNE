"""
Tests de integración para services/extraccion/main.py — Flujo completo con TestClient.

Verifica:
- Documento pequeño → CSV generado + persistencia en Supabase (background)
- Segundo upload del mismo archivo → HTTP 409 (duplicado bloqueado)
- Chunk 1 falla 3x → estado "partial" en sesión
- Documento grande → chunks guardados en BD durante procesamiento

Todos los tests usan mocks para:
- No hacer requests reales a Gemini
- No hacer requests reales a Supabase
"""

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import services.extraccion.supabase_client as sc_module
from services.extraccion.auth import UsuarioPerfil, get_current_user
from services.extraccion.main import app

# Auth obligatoria (extraccion-multi-tenant, T1): /procesar y /api/documentos ya no
# aceptan caller anónimo -- el HTML viejo que lo hacía se retira en T2. Estos tests
# ejercitan el flujo de negocio (upload/parsing/persistencia), no el gate de auth en
# sí (eso vive en tests/test_extraccion_auth.py), así que autentican con un usuario
# fijo vía dependency_override.


# ---------------------------------------------------------------------------
# Fixtures globales
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_supabase_singleton():
    """Resetea el singleton de Supabase antes de cada test de integración."""
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()


@pytest.fixture(autouse=True)
def _autenticado():
    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id="usuario-test", drogueria_id="drogueria-test", rol="comercial"
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client():
    """TestClient de FastAPI para tests sincrónicos."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def headers_json():
    """Headers para requests que esperan respuesta JSON."""
    return {"Accept": "application/json"}


@pytest.fixture
def pdf_bytes():
    """Contenido binario simulado de un PDF pequeño."""
    return b"%PDF-1.4 contenido de prueba para test de integracion"


@pytest.fixture
def xlsx_bytes():
    """Contenido binario simulado de un XLSX."""
    return b"PK\x03\x04contenido xlsx de prueba para test de integracion"


# ---------------------------------------------------------------------------
# Helpers de mock comunes
# ---------------------------------------------------------------------------

def _mock_csv_output(tmp_path: Path, contenido: str = "") -> Path:
    """Crea un CSV temporal que el robot devolvería como resultado."""
    csv_path = tmp_path / "resultado.csv"
    csv_path.write_text(
        "proveedor;precio\nACME;100\nXYZ;200\n" if not contenido else contenido,
        encoding="utf-8",
    )
    return csv_path


# ---------------------------------------------------------------------------
# 4.5.1 — Documento pequeño → CSV generado + stored en Supabase
# ---------------------------------------------------------------------------

class TestProcesarFileSmallSuccess:
    """Test 4.5.1: documento pequeño procesado exitosamente."""

    def test_procesar_file_small_success(
        self, client, headers_json, pdf_bytes, tmp_path, mocker
    ):
        """
        Dado un PDF pequeño válido:
        1. calcular_sha256 corre sin error
        2. buscar_duplicado_con_lock retorna None (no es duplicado)
        3. crear_sesion retorna UUID
        4. procesar_archivo retorna un CSV válido
        5. schedule_persist_output registra la background task
        6. La respuesta HTTP es 200 con ok=True
        """
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        # Mock SHA256 — operación rápida sin acceso a disco real
        mocker.patch(
            "services.extraccion.main.calcular_sha256",
            return_value="a" * 64,
        )
        # Sin duplicado
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        # Sesión creada exitosamente
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        # Robot retorna el CSV sin llamar a Gemini
        mocker.patch(
            "services.extraccion.main.procesar_archivo",
            return_value=str(csv_path),
        )
        # Background task registrada (no ejecutamos la task real)
        mock_schedule = mocker.patch(
            "services.extraccion.main.schedule_persist_output",
            new_callable=AsyncMock,
        )

        response = client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("documento.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        mock_schedule.assert_awaited_once()


# ---------------------------------------------------------------------------
# 4.5.2 — Segundo upload igual → HTTP 409
# ---------------------------------------------------------------------------

class TestProcesarFileDuplicateBlocks:
    """Test 4.5.2: segundo upload del mismo archivo devuelve 409."""

    def test_procesar_file_duplicate_blocks_second(
        self, client, headers_json, pdf_bytes, mocker
    ):
        """
        Cuando buscar_duplicado_con_lock retorna un UUID existente →
        la respuesta debe ser HTTP 409 con error de duplicado.
        """
        existing_uuid = uuid.uuid4()

        mocker.patch(
            "services.extraccion.main.calcular_sha256",
            return_value="a" * 64,
        )
        # El duplicado ya existe
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=existing_uuid,
        )

        response = client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("documento.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 409
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["ok"] is False
        assert "procesado" in body["error"].lower() or "duplicado" in body["error"].lower()
        # Bug pre-existente (T2, odd/tasks/extraccion-multi-tenant.md): el 409 de
        # duplicado perdía extraction_id al armar el JSON -- el frontend lo necesita
        # (mismo id que buscar_duplicado_con_lock encontró).
        assert body["extraction_id"] == str(existing_uuid)


# ---------------------------------------------------------------------------
# 4.5.3 — Gemini falla en chunk 1 (robot lanza excepción)
# ---------------------------------------------------------------------------

class TestProcesarFileGeminiFailsChunk1:
    """Test 4.5.3: el robot lanza excepción → respuesta de error apropiada."""

    def test_procesar_file_gemini_fails_chunk_1(
        self, client, headers_json, pdf_bytes, mocker
    ):
        """
        Cuando el robot lanza una excepción genérica (simulando fallo de Gemini) →
        la respuesta HTTP es 500 con ok=False.
        La sesión debería quedar en estado "partial" (no verificamos BD aquí,
        solo el HTTP response del endpoint).
        """
        session_uuid = uuid.uuid4()

        mocker.patch(
            "services.extraccion.main.calcular_sha256",
            return_value="b" * 64,
        )
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        # Robot falla con excepción genérica
        mocker.patch(
            "services.extraccion.main.procesar_archivo",
            side_effect=RuntimeError("Gemini chunk 1 failed after 3 retries"),
        )

        response = client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("comparativa.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 500
        body = response.json()
        assert body["ok"] is False


# ---------------------------------------------------------------------------
# 4.5.4 — Documento grande (comparativa) → chunks guardados en BD
# ---------------------------------------------------------------------------

class TestProcesarComparativaChunksSavings:
    """Test 4.5.4: comparativa procesada → se schedulea persistencia."""

    def test_procesar_comparativa_chunks_savings(
        self, client, headers_json, xlsx_bytes, tmp_path, mocker
    ):
        """
        Dado un XLSX de comparativa SIN licitacion_id (la vinculación a un proceso
        comercial no se exige en /procesar — es una decisión de negocio que se resuelve
        en "Validar extracción", ver openspec/changes/validar-extraccion/proposal.md):
        1. crear_sesion retorna UUID de sesión
        2. procesar_comparativa retorna CSV
        3. schedule_persist_output es llamado con session_id y doc_type='comparativa'
        Esto confirma que los chunks de la sesión son persistibles.
        """
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch(
            "services.extraccion.main.calcular_sha256",
            return_value="c" * 64,
        )
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        # Robot de comparativas retorna CSV exitosamente
        mocker.patch(
            "services.extraccion.main.procesar_comparativa",
            return_value=str(csv_path),
        )
        mock_schedule = mocker.patch(
            "services.extraccion.main.schedule_persist_output",
            new_callable=AsyncMock,
        )

        response = client.post(
            "/procesar",
            data={"tipo": "comparativas"},
            files={
                "archivo": (
                    "comparativa_mayo.xlsx",
                    io.BytesIO(xlsx_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            headers=headers_json,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True

        # Verificamos que schedule_persist_output fue llamado con doc_type correcto
        mock_schedule.assert_awaited_once()
        kwargs = mock_schedule.await_args.kwargs
        assert kwargs["doc_type"] == "comparativa"
        assert kwargs["session_id"] == session_uuid


# ---------------------------------------------------------------------------
# SC-23 — licitacion_id válido → propagado a schedule_persist_output
# ---------------------------------------------------------------------------

class TestProcesarConLicitacionIdValido:
    """SC-23: licitacion_id en el form → llega como kwarg a schedule_persist_output."""

    def test_licitacion_id_propagado(
        self, client, headers_json, pdf_bytes, tmp_path, mocker
    ):
        session_uuid = uuid.uuid4()
        lic_id = str(uuid.uuid4())
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="d" * 64)
        mocker.patch("services.extraccion.main.buscar_duplicado_con_lock", new_callable=AsyncMock, return_value=None)
        mocker.patch("services.extraccion.main.crear_sesion", new_callable=AsyncMock, return_value=session_uuid)
        mocker.patch("services.extraccion.main.procesar_archivo", return_value=str(csv_path))
        # validar_proceso_comercial_id retorna el mismo id (ya existe en BD, misma droguería)
        mocker.patch(
            "services.extraccion.main.validar_proceso_comercial_id",
            new_callable=AsyncMock,
            return_value=lic_id,
        )
        mock_schedule = mocker.patch("services.extraccion.main.schedule_persist_output", new_callable=AsyncMock)

        response = client.post(
            "/procesar",
            data={"tipo": "", "licitacion_id": lic_id},
            files={"archivo": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 200
        mock_schedule.assert_awaited_once()
        assert mock_schedule.await_args.kwargs["licitacion_id"] == lic_id


# ---------------------------------------------------------------------------
# SC-24 — licitacion_id vacío → None propagado
# ---------------------------------------------------------------------------

class TestProcesarSinLicitacionId:
    """SC-24: sin licitacion_id en el form → None en schedule_persist_output."""

    def test_licitacion_id_none_cuando_vacio(
        self, client, headers_json, pdf_bytes, tmp_path, mocker
    ):
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="e" * 64)
        mocker.patch("services.extraccion.main.buscar_duplicado_con_lock", new_callable=AsyncMock, return_value=None)
        mocker.patch("services.extraccion.main.crear_sesion", new_callable=AsyncMock, return_value=session_uuid)
        mocker.patch("services.extraccion.main.procesar_archivo", return_value=str(csv_path))
        # Vacío → validar_proceso_comercial_id retorna None
        mocker.patch(
            "services.extraccion.main.validar_proceso_comercial_id",
            new_callable=AsyncMock,
            return_value=None,
        )
        mock_schedule = mocker.patch("services.extraccion.main.schedule_persist_output", new_callable=AsyncMock)

        response = client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 200
        assert mock_schedule.await_args.kwargs["licitacion_id"] is None


# ---------------------------------------------------------------------------
# SC-25 — fail-fast: licitacion_id inválido → 422, robot NO invocado
# ---------------------------------------------------------------------------

class TestProcesarLicitacionIdInvalido:
    """SC-25: licitacion_id que no existe → 422 antes de invocar robot/Gemini."""

    def test_uuid_no_existente_retorna_422_sin_llamar_robot(
        self, client, headers_json, pdf_bytes, mocker
    ):
        from fastapi import HTTPException

        mocker.patch(
            "services.extraccion.main.validar_proceso_comercial_id",
            new_callable=AsyncMock,
            side_effect=HTTPException(
                status_code=422,
                detail="Proceso comercial <uuid> no existe",
            ),
        )
        mock_robot = mocker.patch("services.extraccion.main.procesar_archivo")

        response = client.post(
            "/procesar",
            data={"tipo": "", "licitacion_id": str(uuid.uuid4())},
            files={"archivo": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 422
        mock_robot.assert_not_called()

    def test_uuid_malformado_retorna_422_sin_llamar_robot(
        self, client, headers_json, pdf_bytes, mocker
    ):
        from fastapi import HTTPException

        mocker.patch(
            "services.extraccion.main.validar_proceso_comercial_id",
            new_callable=AsyncMock,
            side_effect=HTTPException(
                status_code=422,
                detail="licitacion_id no es un UUID válido: no-es-uuid",
            ),
        )
        mock_robot = mocker.patch("services.extraccion.main.procesar_archivo")

        response = client.post(
            "/procesar",
            data={"tipo": "", "licitacion_id": "no-es-uuid"},
            files={"archivo": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 422
        mock_robot.assert_not_called()


# ---------------------------------------------------------------------------
# tipo="ordenes" -> tercer tipo de documento soportado (Tramo 1, D13): ya NO
# se rechaza con 422 — invoca al robot dedicado procesar_orden_compra.
# ---------------------------------------------------------------------------

class TestProcesarTipoOrdenes:
    """Orden de Compra: tercer tipo de documento soportado, con agrupación (D13)."""

    def test_tipo_ordenes_no_devuelve_422_e_invoca_robot_orden_compra(
        self, client, headers_json, pdf_bytes, tmp_path, mocker
    ):
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="f" * 64)
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        mock_orden_compra = mocker.patch(
            "services.extraccion.main.procesar_orden_compra",
            return_value=str(csv_path),
        )
        mock_schedule = mocker.patch(
            "services.extraccion.main.schedule_persist_output", new_callable=AsyncMock
        )

        response = client.post(
            "/procesar",
            data={"tipo": "ordenes"},
            files={"archivo": ("orden.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code != 422
        assert response.status_code == 200
        mock_orden_compra.assert_called_once()
        mock_schedule.assert_awaited_once()
        assert mock_schedule.await_args.kwargs["doc_type"] == "orden_compra"

    def test_tipo_ordenes_acepta_html(
        self, client, headers_json, tmp_path, mocker
    ):
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="1" * 64)
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        mocker.patch(
            "services.extraccion.main.procesar_orden_compra", return_value=str(csv_path)
        )
        mocker.patch(
            "services.extraccion.main.schedule_persist_output", new_callable=AsyncMock
        )

        response = client.post(
            "/procesar",
            data={"tipo": "ordenes"},
            files={"archivo": ("orden.html", io.BytesIO(b"<html>orden</html>"), "text/html")},
            headers=headers_json,
        )

        assert response.status_code == 200

    def test_tipo_ordenes_acepta_htm(
        self, client, headers_json, tmp_path, mocker
    ):
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="2" * 64)
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        mocker.patch(
            "services.extraccion.main.procesar_orden_compra", return_value=str(csv_path)
        )
        mocker.patch(
            "services.extraccion.main.schedule_persist_output", new_callable=AsyncMock
        )

        response = client.post(
            "/procesar",
            data={"tipo": "ordenes"},
            files={"archivo": ("orden.htm", io.BytesIO(b"<html>orden</html>"), "text/html")},
            headers=headers_json,
        )

        assert response.status_code == 200

    def test_grupo_id_invalido_retorna_422_sin_llamar_robot(
        self, client, headers_json, pdf_bytes, mocker
    ):
        """D13: grupo_id que no tiene forma de UUID v4 se rechaza fail-fast, antes de
        cualquier I/O o invocación a Gemini (mismo patrón que licitacion_id, SC-25)."""
        mock_robot = mocker.patch("services.extraccion.main.procesar_orden_compra")

        response = client.post(
            "/procesar",
            data={"tipo": "ordenes", "grupo_id": "no-es-un-uuid"},
            files={"archivo": ("orden.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 422
        mock_robot.assert_not_called()

    def test_grupo_id_ausente_se_comporta_como_extraccion_suelta(
        self, client, headers_json, pdf_bytes, tmp_path, mocker
    ):
        """D13: sin grupo_id, el comportamiento es idéntico al de una extracción sin
        capacidad de agrupación — None llega a schedule_persist_output."""
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="3" * 64)
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        mocker.patch(
            "services.extraccion.main.procesar_orden_compra", return_value=str(csv_path)
        )
        mock_schedule = mocker.patch(
            "services.extraccion.main.schedule_persist_output", new_callable=AsyncMock
        )

        response = client.post(
            "/procesar",
            data={"tipo": "ordenes"},
            files={"archivo": ("orden.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 200
        assert mock_schedule.await_args.kwargs["grupo_id"] is None

    def test_grupo_id_valido_se_propaga_a_schedule_persist_output(
        self, client, headers_json, pdf_bytes, tmp_path, mocker
    ):
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)
        grupo_id = str(uuid.uuid4())

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="4" * 64)
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        mocker.patch(
            "services.extraccion.main.procesar_orden_compra", return_value=str(csv_path)
        )
        mock_schedule = mocker.patch(
            "services.extraccion.main.schedule_persist_output", new_callable=AsyncMock
        )

        response = client.post(
            "/procesar",
            data={"tipo": "ordenes", "grupo_id": grupo_id},
            files={"archivo": ("orden.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 200
        assert mock_schedule.await_args.kwargs["grupo_id"] == grupo_id

    def test_grupo_id_ignorado_si_tipo_no_es_ordenes(
        self, client, headers_json, pdf_bytes, tmp_path, mocker
    ):
        """D13: grupo_id se ignora por completo fuera de tipo=ordenes — ni se valida
        ni se propaga, aunque venga en el form."""
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="5" * 64)
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        mocker.patch("services.extraccion.main.procesar_archivo", return_value=str(csv_path))
        mock_schedule = mocker.patch(
            "services.extraccion.main.schedule_persist_output", new_callable=AsyncMock
        )

        response = client.post(
            "/procesar",
            data={"tipo": "", "grupo_id": "esto-no-es-un-uuid-pero-no-deberia-importar"},
            files={"archivo": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers_json,
        )

        assert response.status_code == 200
        assert mock_schedule.await_args.kwargs["grupo_id"] is None


# ---------------------------------------------------------------------------
# SC-27 — GET /api/documentos incluye campo proceso_comercial
# ---------------------------------------------------------------------------
#
# Desde el change carga-documentos, el nombre ya NO se resuelve con un embed de
# Supabase contra "licitaciones" (tabla inexistente) sino con una query aparte,
# escopeada por drogueria_id, vía procesos_comerciales_client.listar_nombres_procesos_comerciales.

class TestListarDocumentosConLicitacion:
    """SC-27: GET /api/documentos → campo proceso_comercial resuelto vía procesos_comerciales_client."""

    def test_documentos_incluyen_campo_proceso_comercial(self, client, mocker):
        from unittest.mock import MagicMock

        proceso_id = str(uuid.uuid4())
        doc_row = {
            "id": str(uuid.uuid4()),
            "source_filename": "doc.pdf",
            "document_type": "licitacion",
            "client_id": "cliente1",
            "row_count": 5,
            "status": "completed",
            "created_at": "2026-05-14T10:00:00+00:00",
            "proceso_comercial_id": proceso_id,
        }

        mock_result = MagicMock()
        mock_result.data = [doc_row]
        mock_qb = MagicMock()
        mock_qb.select.return_value = mock_qb
        mock_qb.eq.return_value = mock_qb
        mock_qb.order.return_value = mock_qb
        mock_qb.execute.return_value = mock_result

        mock_client = MagicMock()
        mock_client.table.return_value = mock_qb
        mocker.patch("services.extraccion.main.get_client", return_value=mock_client)
        mocker.patch(
            "services.extraccion.main.listar_nombres_procesos_comerciales",
            new_callable=AsyncMock,
            return_value={proceso_id: "Lic. Trimestral"},
        )

        response = client.get("/api/documentos")

        assert response.status_code == 200
        docs = response.json()["documentos"]
        assert len(docs) == 1
        assert docs[0]["proceso_comercial"] == {"id": proceso_id, "nombre": "Lic. Trimestral"}
        assert "proceso_comercial_id" not in docs[0]

    def test_documentos_sin_proceso_comercial_son_none(self, client, mocker):
        from unittest.mock import MagicMock

        doc_row = {
            "id": str(uuid.uuid4()),
            "source_filename": "comparativa.xlsx",
            "document_type": "comparativa",
            "client_id": "cliente2",
            "row_count": 3,
            "status": "completed",
            "created_at": "2026-05-14T10:00:00+00:00",
            "proceso_comercial_id": None,
        }

        mock_result = MagicMock()
        mock_result.data = [doc_row]
        mock_qb = MagicMock()
        mock_qb.select.return_value = mock_qb
        mock_qb.eq.return_value = mock_qb
        mock_qb.order.return_value = mock_qb
        mock_qb.execute.return_value = mock_result

        mock_client = MagicMock()
        mock_client.table.return_value = mock_qb
        mocker.patch("services.extraccion.main.get_client", return_value=mock_client)
        mocker.patch(
            "services.extraccion.main.listar_nombres_procesos_comerciales",
            new_callable=AsyncMock,
            return_value={},
        )

        response = client.get("/api/documentos")

        assert response.status_code == 200
        docs = response.json()["documentos"]
        assert docs[0]["proceso_comercial"] is None

    def test_proceso_comercial_de_otra_drogueria_se_muestra_como_none(self, client, mocker):
        """Si listar_nombres_procesos_comerciales no devuelve el id (filtrado por
        drogueria_id, ver procesos_comerciales_client.py), el documento se muestra
        como sin vincular — nunca con el nombre real de un proceso de otra droguería."""
        from unittest.mock import MagicMock

        proceso_id_de_otra_drogueria = str(uuid.uuid4())
        doc_row = {
            "id": str(uuid.uuid4()),
            "source_filename": "doc.pdf",
            "document_type": "licitacion",
            "client_id": "cliente1",
            "row_count": 5,
            "status": "completed",
            "created_at": "2026-05-14T10:00:00+00:00",
            "proceso_comercial_id": proceso_id_de_otra_drogueria,
        }

        mock_result = MagicMock()
        mock_result.data = [doc_row]
        mock_qb = MagicMock()
        mock_qb.select.return_value = mock_qb
        mock_qb.eq.return_value = mock_qb
        mock_qb.order.return_value = mock_qb
        mock_qb.execute.return_value = mock_result

        mock_client = MagicMock()
        mock_client.table.return_value = mock_qb
        mocker.patch("services.extraccion.main.get_client", return_value=mock_client)
        # El id no aparece en el dict devuelto -> filtrado por drogueria_id en la query real
        mocker.patch(
            "services.extraccion.main.listar_nombres_procesos_comerciales",
            new_callable=AsyncMock,
            return_value={},
        )

        response = client.get("/api/documentos")

        assert response.status_code == 200
        docs = response.json()["documentos"]
        assert docs[0]["proceso_comercial"] is None


# ---------------------------------------------------------------------------
# T2 (odd/tasks/extraccion-multi-tenant.md) — legacy HTML retirado: las rutas
# que servían pantallas Jinja2 y los endpoints legacy-only ya no existen.
# ---------------------------------------------------------------------------

class TestRutasLegacyRetiradas:
    """Las pantallas HTML viejas y los endpoints que solo ellas consumían
    responden 404 -- no hay ningún handler registrado en esas rutas."""

    @pytest.mark.parametrize(
        "metodo,ruta",
        [
            ("get", "/"),
            ("get", "/upload"),
            ("get", "/licitaciones"),
            ("get", "/calendario"),
            ("get", "/historial"),
            ("get", "/guia"),
            ("get", "/descargar/algo.csv"),
            ("get", f"/api/documentos/{uuid.uuid4()}/descargar"),
            ("get", "/api/licitaciones"),
            ("get", "/api/licitaciones/activas"),
        ],
    )
    def test_ruta_legacy_devuelve_404(self, client, metodo, ruta):
        response = getattr(client, metodo)(ruta)
        assert response.status_code == 404

    def test_static_no_esta_montado(self, client):
        response = client.get("/static/main.js")
        assert response.status_code == 404
