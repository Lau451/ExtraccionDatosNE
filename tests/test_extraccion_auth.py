"""Tests de autenticación obligatoria + scoping por droguería de
services/extraccion/ — services/extraccion/auth.py, main.py, background_tasks.py,
persistent_output.py.

Cubre el checklist de TDD de odd/tasks/extraccion-multi-tenant.md (T1):
- /procesar sin token -> 401
- /procesar enhebra drogueria_id del usuario autenticado a crear_sesion y a
  schedule_persist_output
- GET /api/documentos filtra por droguería
- detalle de otra droguería -> 404
- PATCH de otra droguería -> 404
- buscar_duplicado_con_lock recibe drogueria_id (dedup por tenant)
- el 409 nunca puede devolver un extraction_id de otra droguería (a nivel de
  contrato: buscar_duplicado_con_lock siempre se llama con LA droguería del caller)
"""
import io
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import services.extraccion.supabase_client as sc_module
from services.extraccion.auth import UsuarioPerfil, get_current_user
from services.extraccion.main import app

USUARIO_A = UsuarioPerfil(id="usuario-a", drogueria_id="drogueria-a", rol="comercial")
USUARIO_B = UsuarioPerfil(id="usuario-b", drogueria_id="drogueria-b", rol="comercial")


@pytest.fixture(autouse=True)
def reset_supabase():
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def _autenticar_como(usuario: UsuarioPerfil) -> None:
    app.dependency_overrides[get_current_user] = lambda: usuario


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4 contenido de prueba"


# ---------------------------------------------------------------------------
# Auth obligatoria: sin token -> 401
# ---------------------------------------------------------------------------

class TestAuthObligatoria:
    def test_procesar_sin_token_devuelve_401(self, client):
        response = client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("doc.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
            headers={"Accept": "application/json"},
        )

        assert response.status_code == 401

    def test_listar_documentos_sin_token_devuelve_401(self, client):
        response = client.get("/api/documentos")

        assert response.status_code == 401

    def test_detalle_documento_sin_token_devuelve_401(self, client):
        response = client.get(f"/api/documentos/{uuid.uuid4()}")

        assert response.status_code == 401

    def test_patch_extraction_result_sin_token_devuelve_401(self, client):
        response = client.patch(
            f"/api/extraction-results/{uuid.uuid4()}",
            json={"document_type": "comparativa"},
        )

        assert response.status_code == 401

    def test_listar_clientes_sin_token_devuelve_401(self, client):
        response = client.get("/api/clientes")

        assert response.status_code == 401

    def test_usuario_sin_drogueria_asignada_devuelve_403(self, client):
        _autenticar_como(UsuarioPerfil(id="huerfano", drogueria_id=None, rol="comercial"))

        response = client.get("/api/documentos")

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# /procesar enhebra drogueria_id explícitamente (sin resolver_drogueria_id_unica)
# ---------------------------------------------------------------------------

class TestProcesarEnhebraDrogueriaId:
    def test_procesar_pasa_drogueria_id_del_usuario_a_crear_sesion_y_persistencia(
        self, client, tmp_path, mocker
    ):
        _autenticar_como(USUARIO_A)
        session_uuid = uuid.uuid4()
        csv_path = tmp_path / "resultado.csv"
        csv_path.write_text("proveedor;precio\nACME;100\n", encoding="utf-8")

        mocker.patch("services.extraccion.main.calcular_sha256", return_value="a" * 64)
        mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock, return_value=None,
        )
        mock_crear_sesion = mocker.patch(
            "services.extraccion.main.crear_sesion",
            new_callable=AsyncMock, return_value=session_uuid,
        )
        mocker.patch("services.extraccion.main.procesar_archivo", return_value=str(csv_path))
        mock_schedule = mocker.patch(
            "services.extraccion.main.schedule_persist_output", new_callable=AsyncMock,
        )

        response = client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("doc.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
            headers={"Accept": "application/json"},
        )

        assert response.status_code == 200
        assert mock_crear_sesion.await_args.kwargs["drogueria_id"] == "drogueria-a"
        assert mock_crear_sesion.await_args.kwargs["subido_por"] == "usuario-a"
        assert mock_schedule.await_args.kwargs["drogueria_id"] == "drogueria-a"

    def test_procesar_pasa_drogueria_id_a_buscar_duplicado_con_lock(
        self, client, mocker
    ):
        _autenticar_como(USUARIO_A)
        mocker.patch("services.extraccion.main.calcular_sha256", return_value="b" * 64)
        mock_dup = mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock, return_value=None,
        )
        mocker.patch(
            "services.extraccion.main.crear_sesion", new_callable=AsyncMock, return_value=uuid.uuid4(),
        )
        mocker.patch("services.extraccion.main.procesar_archivo", side_effect=RuntimeError("stop"))

        client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("doc.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
            headers={"Accept": "application/json"},
        )

        assert mock_dup.await_args.kwargs["drogueria_id"] == "drogueria-a"

    def test_409_solo_puede_devolver_extraction_id_de_la_propia_drogueria(
        self, client, mocker
    ):
        """No hay forma de ejercitar el filtrado real de la RPC en un test unitario
        (eso vive en la migración 0027 / test de integración), pero acá se prueba
        el contrato del lado del caller: buscar_duplicado_con_lock SIEMPRE se llama
        con la droguería del usuario autenticado -- nunca con la de otro, así que un
        409 nunca puede filtrar el id de un duplicado ajeno."""
        _autenticar_como(USUARIO_B)
        mocker.patch("services.extraccion.main.calcular_sha256", return_value="c" * 64)
        existing_id = uuid.uuid4()
        mock_dup = mocker.patch(
            "services.extraccion.main.buscar_duplicado_con_lock",
            new_callable=AsyncMock, return_value=existing_id,
        )

        response = client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("doc.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
            headers={"Accept": "application/json"},
        )

        assert response.status_code == 409
        # El único filtro de tenant posible en el 409 es el que ya viaja en la
        # llamada a buscar_duplicado_con_lock: siempre la droguería del caller.
        assert mock_dup.await_args.kwargs["drogueria_id"] == "drogueria-b"


# ---------------------------------------------------------------------------
# GET /api/documentos filtra por droguería
# ---------------------------------------------------------------------------

class TestListarDocumentosFiltraPorDrogueria:
    def test_query_incluye_eq_drogueria_id(self, client, mocker):
        _autenticar_como(USUARIO_A)
        mock_qb = MagicMock()
        mock_qb.select.return_value = mock_qb
        mock_qb.eq.return_value = mock_qb
        mock_qb.order.return_value = mock_qb
        mock_qb.execute.return_value = MagicMock(data=[])
        mock_client = MagicMock()
        mock_client.table.return_value = mock_qb
        mocker.patch("services.extraccion.main.get_client", return_value=mock_client)

        response = client.get("/api/documentos")

        assert response.status_code == 200
        mock_qb.eq.assert_any_call("drogueria_id", "drogueria-a")


# ---------------------------------------------------------------------------
# Detalle de otra droguería -> 404
# ---------------------------------------------------------------------------

class TestDetalleDocumentoOtraDrogueria:
    def test_detalle_de_otra_drogueria_da_404(self, client, mocker):
        """El query real filtra por drogueria_id; si el doc pertenece a otra
        droguería, el SELECT no matchea ninguna fila -- 404, igual que un id
        inexistente (no distingue los dos casos, no filtra existencia)."""
        _autenticar_como(USUARIO_A)
        mock_qb = MagicMock()
        for m in ("select", "eq", "limit"):
            getattr(mock_qb, m).return_value = mock_qb
        mock_qb.execute.return_value = MagicMock(data=[])
        mock_client = MagicMock()
        mock_client.table.return_value = mock_qb
        mocker.patch("services.extraccion.main.get_client", return_value=mock_client)

        response = client.get(f"/api/documentos/{uuid.uuid4()}")

        assert response.status_code == 404
        mock_qb.eq.assert_any_call("drogueria_id", "drogueria-a")


# ---------------------------------------------------------------------------
# PATCH de otra droguería -> 404
# ---------------------------------------------------------------------------

class TestPatchExtractionResultOtraDrogueria:
    def test_patch_de_otra_drogueria_da_404(self, client, mocker):
        _autenticar_como(USUARIO_A)
        mock_qb = MagicMock()
        for m in ("update", "select", "eq", "limit"):
            getattr(mock_qb, m).return_value = mock_qb
        mock_qb.execute.return_value = MagicMock(data=[])  # UPDATE no matchea ninguna fila
        mock_client = MagicMock()
        mock_client.table.return_value = mock_qb
        mocker.patch(
            "services.extraccion.routers.extraction_results.get_client",
            return_value=mock_client,
        )

        response = client.patch(
            f"/api/extraction-results/{uuid.uuid4()}",
            json={"document_type": "comparativa"},
        )

        assert response.status_code == 404
        mock_qb.eq.assert_any_call("drogueria_id", "drogueria-a")


# ---------------------------------------------------------------------------
# Dedup: la RPC recibe drogueria_id
# ---------------------------------------------------------------------------

class TestBuscarDuplicadoConLockRecibeDrogueriaId:
    @pytest.mark.asyncio
    async def test_rpc_reserve_extraction_recibe_p_drogueria_id(self, mocker):
        from services.extraccion import persistent_output

        mock_client = MagicMock()
        mock_client.rpc.return_value.execute.return_value.data = None
        mocker.patch("services.extraccion.persistent_output.get_client", return_value=mock_client)

        await persistent_output.buscar_duplicado_con_lock(
            source_sha256="d" * 64, drogueria_id="drogueria-a"
        )

        mock_client.rpc.assert_called_once_with(
            "reserve_extraction", {"p_sha": "d" * 64, "p_drogueria_id": "drogueria-a"}
        )


@pytest.mark.integration
def test_reserve_extraction_no_filtra_duplicado_de_otra_drogueria(
    service_client, seed_drogueria, seed_extraction_result_factory,
):
    """No puede pasar hasta que el padre aplique la migración 0027 a Supabase TEST
    (grnamollopxdlstcpxhc) -- reserve_extraction(p_sha, p_drogueria_id) todavía no
    existe con esa firma en la base real. Prueba contra la RPC real: un duplicado en
    OTRA droguería no debe bloquear un upload en la propia."""
    import secrets

    sha = secrets.token_hex(32)
    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería (dedup test)",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": "otra-dedup@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]

    try:
        service_client.table("extraction_results").insert(
            {
                "drogueria_id": otra_drogueria["id"],
                "document_type": "licitacion",
                "source_filename": "ajeno.pdf",
                "source_sha256": sha,
                "row_count": 1,
                "status": "completed",
            }
        ).execute()

        resultado = service_client.rpc(
            "reserve_extraction", {"p_sha": sha, "p_drogueria_id": seed_drogueria["id"]}
        ).execute()

        assert resultado.data is None  # sin duplicado EN LA PROPIA droguería
    finally:
        service_client.table("extraction_results").delete().eq("source_sha256", sha).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()
