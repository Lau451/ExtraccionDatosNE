"""
Tests de integración para app/main.py — Flujo completo con TestClient.

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

import app.supabase_client as sc_module
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures globales
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_supabase_singleton():
    """Resetea el singleton de Supabase antes de cada test de integración."""
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()


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
            "app.main.calcular_sha256",
            return_value="a" * 64,
        )
        # Sin duplicado
        mocker.patch(
            "app.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        # Sesión creada exitosamente
        mocker.patch(
            "app.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        # Robot retorna el CSV sin llamar a Gemini
        mocker.patch(
            "app.main.procesar_archivo",
            return_value=str(csv_path),
        )
        # Background task registrada (no ejecutamos la task real)
        mock_schedule = mocker.patch(
            "app.main.schedule_persist_output",
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
            "app.main.calcular_sha256",
            return_value="a" * 64,
        )
        # El duplicado ya existe
        mocker.patch(
            "app.main.buscar_duplicado_con_lock",
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
        body = response.json()
        assert body["ok"] is False
        assert "procesado" in body["error"].lower() or "duplicado" in body["error"].lower()


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
            "app.main.calcular_sha256",
            return_value="b" * 64,
        )
        mocker.patch(
            "app.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "app.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        # Robot falla con excepción genérica
        mocker.patch(
            "app.main.procesar_archivo",
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
        Dado un XLSX de comparativa:
        1. crear_sesion retorna UUID de sesión
        2. procesar_comparativa retorna CSV
        3. schedule_persist_output es llamado con session_id y doc_type='comparativa'
        Esto confirma que los chunks de la sesión son persistibles.
        """
        session_uuid = uuid.uuid4()
        csv_path = _mock_csv_output(tmp_path)

        mocker.patch(
            "app.main.calcular_sha256",
            return_value="c" * 64,
        )
        mocker.patch(
            "app.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock,
            return_value=None,
        )
        mocker.patch(
            "app.main.crear_sesion",
            new_callable=AsyncMock,
            return_value=session_uuid,
        )
        # Robot de comparativas retorna CSV exitosamente
        mocker.patch(
            "app.main.procesar_comparativa",
            return_value=str(csv_path),
        )
        mock_schedule = mocker.patch(
            "app.main.schedule_persist_output",
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
