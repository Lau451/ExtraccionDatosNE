"""Tests para services/shared/exceptions.py — 500 JSON con headers CORS ante
excepciones inesperadas (T5, ver odd/tasks/extraccion-multi-tenant.md).

Antes: register_exception_handlers() solo registraba handlers para las subclases de
DomainError (401/403/404/409/422/503). Cualquier excepción no contemplada (p.ej. el
httpx.RemoteProtocolError de una conexión Supabase muerta reusada, ver
services/shared/http_client.py) escapaba de Starlette ExceptionMiddleware -- que
vive DENTRO de CORSMiddleware -- y la recibía ServerErrorMiddleware (fuera de
CORSMiddleware, más externo en el stack). El browser veía un 500 sin encabezados
CORS y mostraba "Failed to fetch" aunque el server sí había respondido (2026-09-25,
oc_sayago.pdf: la extracción se guardó bien, el frontend mostró el error igual).
"""
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from services.shared.exceptions import register_exception_handlers


@pytest.fixture
def app_con_cors() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/explota")
    async def explota():
        raise RuntimeError("boom -- detalle interno que no debe filtrarse")

    return app


def test_excepcion_inesperada_responde_500_json_con_cors(app_con_cors):
    client = TestClient(app_con_cors, raise_server_exceptions=False)

    respuesta = client.get("/explota", headers={"Origin": "http://localhost:5173"})

    assert respuesta.status_code == 500
    assert respuesta.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert respuesta.json() == {"detail": "Error interno del servidor"}


def test_excepcion_inesperada_no_filtra_el_mensaje_original(app_con_cors):
    client = TestClient(app_con_cors, raise_server_exceptions=False)

    respuesta = client.get("/explota", headers={"Origin": "http://localhost:5173"})

    assert "boom" not in respuesta.text
