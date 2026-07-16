"""
Tests para el parámetro licitacion_id en persistent_output.py.

`licitacion_id` (conceptualmente un proceso_comercial_id) SE PERSISTE en la columna
`proceso_comercial_id` de extraction_results (corregido en el change carga-documentos —
antes se aceptaba el parámetro y se descartaba sin escribirlo, dejando siempre NULL la
vinculación). `client_id` y `session_id` siguen sin persistirse — esas sí son compatibilidad
pura, ver el docstring de persistir_output_final para el detalle de por qué.

Verifica que:
- persistir_output_final persiste licitacion_id como proceso_comercial_id en el payload
- licitacion_id=None no agrega la clave proceso_comercial_id al payload (columna nullable)
- schedule_persist_output sigue propagando licitacion_id hacia _retry_persist
"""

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import services.extraccion.supabase_client as sc_module
from services.extraccion import persistent_output
from services.extraccion.background_tasks import schedule_persist_output


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


def _supabase_mock(extraction_uuid: str) -> tuple[MagicMock, dict[str, MagicMock]]:
    """Mock del cliente Supabase: resuelve drogueria_id y simula el INSERT en
    extraction_results como exitoso. Devuelve también el dict de mocks por tabla
    (side_effect crea mocks desconectados del padre — hay que guardar la referencia
    para poder assertear sobre ellos, `mock.mock_calls` no los ve)."""
    mock = MagicMock()
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
                tabla_mock.insert.return_value.execute.return_value.data = [{"id": extraction_uuid}]
            tablas[nombre] = tabla_mock
        return tablas[nombre]

    mock.table.side_effect = _table
    return mock, tablas


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPersistirConLicitacionId:
    @pytest.mark.asyncio
    async def test_licitacion_id_se_persiste_como_proceso_comercial_id(
        self, mocker, rows, csv_path, extraction_uuid
    ):
        """
        Pasar licitacion_id debe persistirlo en el payload de extraction_results bajo la
        columna proceso_comercial_id. client_id y session_id siguen sin persistirse (esos
        sí son compatibilidad pura, no columnas usables en el schema nuevo).
        """
        lic_id = str(uuid.uuid4())
        mock_client, tablas = _supabase_mock(extraction_uuid)
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock_client)

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

        tabla_er = tablas["extraction_results"]
        tabla_er.insert.assert_called_once()
        payload = tabla_er.insert.call_args[0][0]
        assert payload["proceso_comercial_id"] == lic_id
        assert "licitacion_id" not in payload
        assert "client_id" not in payload
        assert "session_id" not in payload

    @pytest.mark.asyncio
    async def test_licitacion_id_none_no_agrega_proceso_comercial_id(
        self, mocker, rows, csv_path, extraction_uuid
    ):
        """licitacion_id=None no debe romper nada, ni agregar la clave proceso_comercial_id
        al payload (columna nullable, se omite en vez de mandar None explícito)."""
        mock_client, tablas = _supabase_mock(extraction_uuid)
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock_client)

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

        payload = tablas["extraction_results"].insert.call_args[0][0]
        assert "proceso_comercial_id" not in payload


class TestSchedulePersistOutputPropagaLicitacionId:
    @pytest.mark.asyncio
    async def test_licitacion_id_propagado_a_background_task(self, mocker):
        """
        schedule_persist_output debe pasar licitacion_id a _retry_persist
        como kwarg en bg.add_task(). Esto no cambió: sigue siendo plomería
        de background_tasks.py, ajena al cambio en el payload de persistencia.
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
