"""
Tests HTTP para PATCH /api/extraction-results/{id}

Escenarios cubiertos:
- Body vacío → 400
- ID inexistente → 404
- document_type inválido ("cotizacion") → 422
- licitacion_id: null → 200, campo null en respuesta
- document_type válido → 200, campo actualizado en respuesta
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import services.extraccion.supabase_client as sc_module
from services.extraccion.main import app


def _qb(execute_result=None):
    qb = MagicMock()
    for m in ("select", "order", "range", "eq", "limit", "update", "insert", "delete"):
        getattr(qb, m).return_value = qb
    qb.execute.return_value = execute_result or MagicMock(data=[], count=0)
    return qb


def _result(data, count=None):
    r = MagicMock()
    r.data = data
    r.count = count if count is not None else len(data)
    return r


_EXT_ROW = {
    "id": str(uuid.uuid4()),
    "document_type": "comparativa",
    "source_filename": "doc.pdf",
    "client_id": "cliente1",
    "row_count": 10,
    "status": "completed",
    "licitacion_id": str(uuid.uuid4()),
    "created_at": "2026-05-14T10:00:00+00:00",
}


@pytest.fixture(autouse=True)
def reset_supabase():
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def ext_id():
    return str(uuid.uuid4())


class TestPatchExtractionResult:
    def test_body_vacio_retorna_400(self, client, ext_id, mocker):
        mocker.patch("services.extraccion.routers.extraction_results.get_client", return_value=MagicMock())

        response = client.patch(f"/api/extraction-results/{ext_id}", json={})

        assert response.status_code == 400

    def test_id_inexistente_retorna_404(self, client, ext_id, mocker):
        qb = _qb(_result([]))
        mc = MagicMock()
        mc.table.return_value = qb
        mocker.patch("services.extraccion.routers.extraction_results.get_client", return_value=mc)

        response = client.patch(
            f"/api/extraction-results/{ext_id}",
            json={"document_type": "comparativa"},
        )

        assert response.status_code == 404

    def test_document_type_invalido_retorna_422(self, client, ext_id, mocker):
        mocker.patch("services.extraccion.routers.extraction_results.get_client", return_value=MagicMock())

        response = client.patch(
            f"/api/extraction-results/{ext_id}",
            json={"document_type": "cotizacion"},
        )

        assert response.status_code == 422

    def test_desvincular_licitacion_retorna_200(self, client, ext_id, mocker):
        updated_row = {**_EXT_ROW, "id": ext_id, "licitacion_id": None}
        qb = _qb()
        qb.execute.side_effect = [_result([updated_row]), _result([updated_row])]
        mc = MagicMock()
        mc.table.return_value = qb
        mocker.patch("services.extraccion.routers.extraction_results.get_client", return_value=mc)

        response = client.patch(
            f"/api/extraction-results/{ext_id}",
            json={"licitacion_id": None},
        )

        assert response.status_code == 200
        assert response.json()["licitacion_id"] is None

    def test_cambiar_document_type_retorna_200(self, client, ext_id, mocker):
        updated_row = {**_EXT_ROW, "id": ext_id, "document_type": "orden_compra"}
        qb = _qb()
        qb.execute.side_effect = [_result([updated_row]), _result([updated_row])]
        mc = MagicMock()
        mc.table.return_value = qb
        mocker.patch("services.extraccion.routers.extraction_results.get_client", return_value=mc)

        response = client.patch(
            f"/api/extraction-results/{ext_id}",
            json={"document_type": "orden_compra"},
        )

        assert response.status_code == 200
        assert response.json()["document_type"] == "orden_compra"
