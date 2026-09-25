"""
Tests HTTP para el router de clientes — services/extraccion/routers/clientes.py

GET /api/clientes nunca debe bloquear ni devolver error al frontend: si Supabase no
está disponible, o no se puede resolver drogueria_id, o la consulta falla, devuelve
lista vacía (el selector de cliente simplemente queda oculto en el upload).

Fase 8 (openspec/changes/terceros-modelo): `clientes.nombre` fue eliminada por la
migración 0008 -- la razón social viene embebida desde `terceros` vía PostgREST
(`fk_cli_tercero`), así que el mock de Supabase debe simular esa forma anidada.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from services.extraccion.auth import UsuarioPerfil, get_current_user
from services.extraccion.main import app

client = TestClient(app)


def _qb(data):
    qb = MagicMock()
    for m in ("select", "eq", "order", "limit"):
        getattr(qb, m).return_value = qb
    qb.execute.return_value = MagicMock(data=data)
    return qb


@pytest.fixture(autouse=True)
def _autenticado():
    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id="usuario-test", drogueria_id="drogueria-1", rol="comercial"
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


class TestListarClientesActivos:
    def test_devuelve_clientes_de_la_drogueria(self, mocker):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = _qb(
            [
                {"id": "cli-1", "terceros": {"razon_social": "Hospital A"}},
                {"id": "cli-2", "terceros": {"razon_social": "Hospital B"}},
            ]
        )
        mocker.patch("services.extraccion.routers.clientes.get_client", return_value=mock_supabase)

        response = client.get("/api/clientes")

        assert response.status_code == 200
        body = response.json()
        assert body == [
            {"id": "cli-1", "nombre": "Hospital A"},
            {"id": "cli-2", "nombre": "Hospital B"},
        ]

    def test_ordena_por_nombre_del_tercero(self, mocker):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = _qb(
            [
                {"id": "cli-2", "terceros": {"razon_social": "Hospital B"}},
                {"id": "cli-1", "terceros": {"razon_social": "Hospital A"}},
            ]
        )
        mocker.patch("services.extraccion.routers.clientes.get_client", return_value=mock_supabase)

        response = client.get("/api/clientes")

        assert response.status_code == 200
        assert [c["nombre"] for c in response.json()] == ["Hospital A", "Hospital B"]

    def test_ignora_filas_sin_tercero_embebido(self, mocker):
        """`fila.get("terceros")` puede venir vacío si el embed de PostgREST
        no resuelve (p.ej. RLS); la fila se descarta en vez de romper con un
        KeyError."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = _qb(
            [
                {"id": "cli-1", "terceros": {"razon_social": "Hospital A"}},
                {"id": "cli-huerfano", "terceros": None},
            ]
        )
        mocker.patch("services.extraccion.routers.clientes.get_client", return_value=mock_supabase)

        response = client.get("/api/clientes")

        assert response.status_code == 200
        assert response.json() == [{"id": "cli-1", "nombre": "Hospital A"}]

    def test_sin_supabase_devuelve_lista_vacia(self, mocker):
        mocker.patch("services.extraccion.routers.clientes.get_client", return_value=None)

        response = client.get("/api/clientes")

        assert response.status_code == 200
        assert response.json() == []

    def test_usuario_sin_drogueria_asignada_devuelve_403(self, mocker):
        """Ya no existe el fallback "sin drogueria resuelta -> lista vacia": si el
        perfil del usuario autenticado no tiene drogueria_id, get_drogueria_id_actual
        corta con 403 antes de tocar Supabase (sin fallback silencioso)."""
        app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
            id="usuario-huerfano", drogueria_id=None, rol="comercial"
        )
        mock_supabase = MagicMock()
        mocker.patch("services.extraccion.routers.clientes.get_client", return_value=mock_supabase)

        response = client.get("/api/clientes")

        assert response.status_code == 403
        mock_supabase.table.assert_not_called()

    def test_error_de_consulta_devuelve_lista_vacia_sin_propagar(self, mocker):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.side_effect = RuntimeError(
            "DB error simulado"
        )
        mocker.patch("services.extraccion.routers.clientes.get_client", return_value=mock_supabase)

        response = client.get("/api/clientes")

        assert response.status_code == 200
        assert response.json() == []
