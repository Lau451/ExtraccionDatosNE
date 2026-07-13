"""
Tests HTTP para el router de clientes — app/routers/clientes.py

GET /api/clientes nunca debe bloquear ni devolver error al frontend: si Supabase no
está disponible, o no se puede resolver drogueria_id, o la consulta falla, devuelve
lista vacía (el selector de cliente simplemente queda oculto en el upload).
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _qb(data):
    qb = MagicMock()
    for m in ("select", "eq", "order", "limit"):
        getattr(qb, m).return_value = qb
    qb.execute.return_value = MagicMock(data=data)
    return qb


class TestListarClientesActivos:
    def test_devuelve_clientes_de_la_drogueria(self, mocker):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = _qb(
            [{"id": "cli-1", "nombre": "Hospital A"}, {"id": "cli-2", "nombre": "Hospital B"}]
        )
        mocker.patch("app.routers.clientes.get_client", return_value=mock_supabase)
        mocker.patch(
            "app.routers.clientes.resolver_drogueria_id_unica", return_value="drogueria-1"
        )

        response = client.get("/api/clientes")

        assert response.status_code == 200
        body = response.json()
        assert body == [
            {"id": "cli-1", "nombre": "Hospital A"},
            {"id": "cli-2", "nombre": "Hospital B"},
        ]

    def test_sin_supabase_devuelve_lista_vacia(self, mocker):
        mocker.patch("app.routers.clientes.get_client", return_value=None)

        response = client.get("/api/clientes")

        assert response.status_code == 200
        assert response.json() == []

    def test_sin_drogueria_resuelta_devuelve_lista_vacia(self, mocker):
        mock_supabase = MagicMock()
        mocker.patch("app.routers.clientes.get_client", return_value=mock_supabase)
        mocker.patch("app.routers.clientes.resolver_drogueria_id_unica", return_value=None)

        response = client.get("/api/clientes")

        assert response.status_code == 200
        assert response.json() == []

    def test_error_de_consulta_devuelve_lista_vacia_sin_propagar(self, mocker):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.side_effect = RuntimeError(
            "DB error simulado"
        )
        mocker.patch("app.routers.clientes.get_client", return_value=mock_supabase)
        mocker.patch(
            "app.routers.clientes.resolver_drogueria_id_unica", return_value="drogueria-1"
        )

        response = client.get("/api/clientes")

        assert response.status_code == 200
        assert response.json() == []
