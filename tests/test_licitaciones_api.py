"""
Tests HTTP para el router de licitaciones — app/routers/licitaciones.py

Escenarios cubiertos:
- Listar (vacío sin Supabase, exitoso, filtros estado/tipo)
- Activas (solo abierta/en_evaluacion, sin Supabase → 503)
- Crear (éxito 201, tipo inválido 422, vencimiento < apertura 422, sin nombre 422)
- Obtener (existe 200 con archivos, no existe 404)
- PATCH (éxito 200, body vacío 400, no existe 404)
- DELETE (sin archivos 204, con archivos 409, no existe 404)
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.supabase_client as sc_module
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _qb(execute_result=None):
    """Mock del query builder de Supabase con API fluente."""
    qb = MagicMock()
    for m in ("select", "order", "range", "eq", "ilike", "in_", "limit", "update",
              "insert", "delete"):
        getattr(qb, m).return_value = qb
    qb.execute.return_value = execute_result or MagicMock(data=[], count=0)
    return qb


def _result(data, count=None):
    r = MagicMock()
    r.data = data
    r.count = count if count is not None else len(data)
    return r


def _mock_client(mocker, *, table_map=None, default_qb=None):
    """
    Patchea app.routers.licitaciones.get_client.
    table_map = {"nombre_tabla": qb_mock} para diferenciar calls por tabla.
    """
    mc = MagicMock()
    if table_map:
        def _side(name):
            return table_map.get(name, default_qb or _qb())
        mc.table.side_effect = _side
    elif default_qb is not None:
        mc.table.return_value = default_qb
    mocker.patch("app.routers.licitaciones.get_client", return_value=mc)
    return mc


# Fila base que devuelve Supabase (archivos_count en formato lista)
_LIC_ROW = {
    "id": str(uuid.uuid4()),
    "nombre": "Licitacion Test",
    "tipo": "medicamentos",
    "apertura": "2026-05-01",
    "vencimiento": "2026-06-01",
    "tipo_gestion": None,
    "modalidad": "mail",
    "estado": "abierta",
    "monto_estimado": None,
    "notas": None,
    "created_at": "2026-05-14T10:00:00+00:00",
    "updated_at": "2026-05-14T10:00:00+00:00",
    "archivos_count": [{"count": 0}],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_supabase():
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def lic_id():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Listar — GET /api/licitaciones
# ---------------------------------------------------------------------------

class TestListarLicitaciones:
    def test_sin_supabase_retorna_503(self, client, mocker):
        mocker.patch("app.routers.licitaciones.get_client", return_value=None)
        response = client.get("/api/licitaciones")
        assert response.status_code == 503

    def test_lista_exitosa(self, client, mocker):
        qb = _qb(_result([_LIC_ROW], count=1))
        _mock_client(mocker, default_qb=qb)

        response = client.get("/api/licitaciones")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["nombre"] == "Licitacion Test"
        assert body["items"][0]["archivos_count"] == 0  # normalizado de [{"count":0}]

    def test_filtro_estado(self, client, mocker):
        qb = _qb(_result([_LIC_ROW], count=1))
        _mock_client(mocker, default_qb=qb)

        response = client.get("/api/licitaciones?estado=abierta")

        assert response.status_code == 200
        qb.eq.assert_any_call("estado", "abierta")

    def test_filtro_tipo(self, client, mocker):
        qb = _qb(_result([_LIC_ROW], count=1))
        _mock_client(mocker, default_qb=qb)

        response = client.get("/api/licitaciones?tipo=medicamentos")

        assert response.status_code == 200
        qb.eq.assert_any_call("tipo", "medicamentos")


# ---------------------------------------------------------------------------
# Activas — GET /api/licitaciones/activas
# ---------------------------------------------------------------------------

class TestListarActivas:
    def test_sin_supabase_retorna_503(self, client, mocker):
        mocker.patch("app.routers.licitaciones.get_client", return_value=None)
        response = client.get("/api/licitaciones/activas")
        assert response.status_code == 503

    def test_retorna_solo_estados_activos(self, client, mocker):
        activa = {"id": str(uuid.uuid4()), "nombre": "Licitacion Activa", "tipo": "descartables"}
        qb = _qb(_result([activa]))
        _mock_client(mocker, default_qb=qb)

        response = client.get("/api/licitaciones/activas")

        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["nombre"] == "Licitacion Activa"
        qb.in_.assert_called_with("estado", ["abierta", "en_evaluacion"])


# ---------------------------------------------------------------------------
# Crear — POST /api/licitaciones
# ---------------------------------------------------------------------------

class TestCrearLicitacion:
    _PAYLOAD = {"nombre": "Nueva Licitacion", "tipo": "medicamentos", "apertura": "2026-08-01"}

    def test_crear_exitoso_retorna_201(self, client, mocker):
        nueva_lic = {**_LIC_ROW, "nombre": "Nueva Licitacion"}
        qb = _qb(_result([nueva_lic]))
        _mock_client(mocker, default_qb=qb)

        response = client.post("/api/licitaciones", json=self._PAYLOAD)

        assert response.status_code == 201
        body = response.json()
        assert body["nombre"] == "Nueva Licitacion"
        assert body["archivos_count"] == 0

    def test_tipo_invalido_retorna_422(self, client, mocker):
        mocker.patch("app.routers.licitaciones.get_client", return_value=MagicMock())

        response = client.post("/api/licitaciones", json={"nombre": "Test", "tipo": "invalido"})

        assert response.status_code == 422

    def test_vencimiento_antes_apertura_retorna_422(self, client, mocker):
        mocker.patch("app.routers.licitaciones.get_client", return_value=MagicMock())

        response = client.post("/api/licitaciones", json={
            "nombre": "Test",
            "tipo": "medicamentos",
            "apertura": "2026-06-01",
            "vencimiento": "2026-05-01",
        })

        assert response.status_code == 422

    def test_sin_nombre_retorna_422(self, client, mocker):
        mocker.patch("app.routers.licitaciones.get_client", return_value=MagicMock())

        response = client.post("/api/licitaciones", json={"tipo": "medicamentos"})

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Obtener — GET /api/licitaciones/{lic_id}
# ---------------------------------------------------------------------------

class TestObtenerLicitacion:
    def test_obtener_existente_con_archivos(self, client, lic_id, mocker):
        lic_row = {**_LIC_ROW, "id": lic_id}
        archivo_row = {
            "id": str(uuid.uuid4()),
            "source_filename": "doc.pdf",
            "document_type": "licitacion",
            "client_id": "cliente1",
            "row_count": 10,
            "status": "completed",
            "created_at": "2026-05-14T10:00:00+00:00",
        }
        qb_lic = _qb(_result([lic_row]))
        qb_arch = _qb(_result([archivo_row]))
        _mock_client(mocker, table_map={
            "licitaciones": qb_lic,
            "extraction_results": qb_arch,
        })

        response = client.get(f"/api/licitaciones/{lic_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == lic_id
        assert len(body["archivos"]) == 1
        assert body["archivos"][0]["source_filename"] == "doc.pdf"

    def test_no_existente_retorna_404(self, client, lic_id, mocker):
        qb = _qb(_result([]))
        _mock_client(mocker, default_qb=qb)

        response = client.get(f"/api/licitaciones/{lic_id}")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Actualizar — PATCH /api/licitaciones/{lic_id}
# ---------------------------------------------------------------------------

class TestActualizarLicitacion:
    def test_patch_exitoso_retorna_200(self, client, lic_id, mocker):
        updated_row = {**_LIC_ROW, "id": lic_id, "estado": "en_evaluacion"}
        qb = _qb()
        # Primera execute = update (truthy data), segunda = re-select
        qb.execute.side_effect = [_result([updated_row]), _result([updated_row])]
        _mock_client(mocker, default_qb=qb)

        response = client.patch(f"/api/licitaciones/{lic_id}", json={"estado": "en_evaluacion"})

        assert response.status_code == 200
        assert response.json()["estado"] == "en_evaluacion"

    def test_body_vacio_retorna_400(self, client, lic_id, mocker):
        mocker.patch("app.routers.licitaciones.get_client", return_value=MagicMock())

        response = client.patch(f"/api/licitaciones/{lic_id}", json={})

        assert response.status_code == 400

    def test_no_existente_retorna_404(self, client, lic_id, mocker):
        qb = _qb(_result([]))  # update retorna vacío → None → 404
        _mock_client(mocker, default_qb=qb)

        response = client.patch(f"/api/licitaciones/{lic_id}", json={"estado": "cerrada"})

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Eliminar — DELETE /api/licitaciones/{lic_id}
# ---------------------------------------------------------------------------

class TestEliminarLicitacion:
    def test_sin_archivos_retorna_204(self, client, lic_id, mocker):
        qb_ext = _qb(_result([], count=0))   # count=0 → no tiene archivos
        qb_lic = _qb(_result([{"id": lic_id}]))  # delete ok
        _mock_client(mocker, table_map={
            "extraction_results": qb_ext,
            "licitaciones": qb_lic,
        })

        response = client.delete(f"/api/licitaciones/{lic_id}")

        assert response.status_code == 204

    def test_con_archivos_retorna_409(self, client, lic_id, mocker):
        qb_ext = _qb(_result([{"id": "arch-1"}], count=1))  # count=1 → tiene archivos
        _mock_client(mocker, default_qb=qb_ext)

        response = client.delete(f"/api/licitaciones/{lic_id}")

        assert response.status_code == 409
        assert "vinculado" in response.json()["detail"].lower()

    def test_no_existente_retorna_404(self, client, lic_id, mocker):
        qb_ext = _qb(_result([], count=0))    # count=0 → no archivos
        qb_lic = _qb(_result([]))             # delete retorna vacío → not_found
        _mock_client(mocker, table_map={
            "extraction_results": qb_ext,
            "licitaciones": qb_lic,
        })

        response = client.delete(f"/api/licitaciones/{lic_id}")

        assert response.status_code == 404
