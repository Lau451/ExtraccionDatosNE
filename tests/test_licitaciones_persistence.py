"""
Tests de persistencia para el campo licitacion_id en persistent_output.py.

Verifica que:
- persistir_output_final incluye licitacion_id en el payload de extraction_results
- licitacion_id=None se persiste sin error (campo nullable)
- schedule_persist_output propaga licitacion_id correctamente
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call

import pytest

import app.supabase_client as sc_module
from app import persistent_output
from app.background_tasks import schedule_persist_output


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "resultado.csv"
    p.write_text("proveedor;precio\nACME;100\n", encoding="utf-8")
    return p


@pytest.fixture
def rows():
    return [{"proveedor": "ACME", "precio": "100"}]


@pytest.fixture
def extraction_uuid():
    return str(uuid.uuid4())


def _supabase_mock(extraction_uuid: str) -> MagicMock:
    """Mock del cliente Supabase que simula INSERT exitoso."""
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": extraction_uuid}
    ]
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPersistirConLicitacionId:
    @pytest.mark.asyncio
    async def test_licitacion_id_incluido_en_payload(
        self, mocker, rows, csv_path, extraction_uuid
    ):
        """
        Cuando persistir_output_final recibe licitacion_id,
        el INSERT en extraction_results incluye ese campo.
        """
        lic_id = str(uuid.uuid4())
        mock_client = _supabase_mock(extraction_uuid)
        mocker.patch("app.persistent_output.get_client", return_value=mock_client)

        result = await persistent_output.persistir_output_final(
            session_id=uuid.uuid4(),
            doc_type="licitacion",
            rows=rows,
            csv_path=csv_path,
            client_id="cliente1",
            source_filename="doc.pdf",
            source_sha256="a" * 64,
            licitacion_id=lic_id,
        )

        assert result is not None
        # call_args_list[0] = primer INSERT = extraction_results (tiene licitacion_id)
        # call_args_list[1] = segundo INSERT = tabla hija
        first_insert = mock_client.table.return_value.insert.call_args_list[0]
        payload = first_insert[0][0]
        assert payload["licitacion_id"] == lic_id

    @pytest.mark.asyncio
    async def test_licitacion_id_none_persiste_sin_error(
        self, mocker, rows, csv_path, extraction_uuid
    ):
        """
        licitacion_id=None → el campo va como None en el payload (FK nullable).
        No debe lanzar excepción ni retornar None.
        """
        mock_client = _supabase_mock(extraction_uuid)
        mocker.patch("app.persistent_output.get_client", return_value=mock_client)

        result = await persistent_output.persistir_output_final(
            session_id=uuid.uuid4(),
            doc_type="licitacion",
            rows=rows,
            csv_path=csv_path,
            client_id="cliente1",
            source_filename="doc.pdf",
            source_sha256="b" * 64,
            licitacion_id=None,
        )

        assert result is not None
        first_insert = mock_client.table.return_value.insert.call_args_list[0]
        payload = first_insert[0][0]
        assert payload["licitacion_id"] is None


class TestSchedulePersistOutputPropagaLicitacionId:
    @pytest.mark.asyncio
    async def test_licitacion_id_propagado_a_background_task(self, mocker):
        """
        schedule_persist_output debe pasar licitacion_id a _retry_persist
        como kwarg en bg.add_task().
        """
        from fastapi import BackgroundTasks
        bg = BackgroundTasks()
        lic_id = str(uuid.uuid4())
        session_id = uuid.uuid4()

        mock_add_task = mocker.patch.object(bg, "add_task")

        await schedule_persist_output(
            bg,
            session_id=session_id,
            doc_type="licitacion",
            rows=[{"col": "val"}],
            csv_path=Path("fake.csv"),
            client_id="cliente1",
            source_filename="doc.pdf",
            source_sha256="c" * 64,
            licitacion_id=lic_id,
        )

        mock_add_task.assert_called_once()
        _, kwargs = mock_add_task.call_args
        assert kwargs["licitacion_id"] == lic_id
