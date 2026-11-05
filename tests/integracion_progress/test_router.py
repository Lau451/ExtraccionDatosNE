"""Router de integracion_progress (odd/tasks/integracion-progress.md S3, S4 manual, S5).

- Tests de contrato HTTP con el usuario inyectado (`get_current_user` sobreescrito) y
  el pipeline reemplazado por un doble: roles, multipart, forma de la respuesta y
  propagación de errores de dominio.
- Tests de integración contra la BD de TEST con JWT real: carga manual de punta a
  punta (registro + import en PCP), duplicado y listado del registro con RLS.
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.integracion_progress import router as router_module
from services.integracion_progress.recepcion.service import ResultadoRecepcion
from services.integracion_progress.registro.models import ErrorLinea, RegistroArchivo
from services.shared.auth import UsuarioPerfil, get_current_user
from services.shared.exceptions import NotFoundError, register_exception_handlers

URL = "/integracion-progress/presupuestos"
ENCABEZADO = (
    "codigo_cliente;razon_social_cliente;numero_presupuesto;renglon;"
    "descripcion_producto;cantidad_producto"
)


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_module.router)
    return app


def _cliente_con_usuario(rol: str, drogueria_id: str | None = "drog-1") -> TestClient:
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id="user-1", drogueria_id=drogueria_id, rol=rol
    )
    return TestClient(app)


def _registro(**campos) -> RegistroArchivo:
    base = {
        "id": "reg-1",
        "drogueria_id": "drog-1",
        "sentido": "entrada",
        "tipo": "presupuestos",
        "nombre_archivo": "presupuestos.csv",
        "sha256": "0" * 64,
        "origen": "manual",
        "estado": "procesado",
        "filas": 1,
        "errores": None,
        "usuario_id": "user-1",
        "intentos": 0,
        "procesado_at": datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc),
    }
    base.update(campos)
    return RegistroArchivo.model_validate(base)


class RecepcionFalsa:
    def __init__(self, resultado=None, error=None):
        self.resultado = resultado
        self.error = error
        self.llamadas: list[dict] = []

    def __call__(self, client, **kwargs):
        self.llamadas.append({"client": client, **kwargs})
        if self.error is not None:
            raise self.error
        return self.resultado


@pytest.fixture
def recepcion_falsa(monkeypatch):
    def _instalar(resultado=None, error=None):
        falsa = RecepcionFalsa(resultado, error)
        monkeypatch.setattr(router_module.recepcion, "recibir_archivo", falsa)
        monkeypatch.setattr(router_module, "get_service_client", lambda: "service-client")
        return falsa

    return _instalar


def _subir(client: TestClient, contenido: bytes = b"x", nombre: str = "presupuestos.csv"):
    return client.post(URL, files={"archivo": (nombre, contenido, "text/csv")})


def test_admin_sube_el_archivo_y_recibe_el_resultado(recepcion_falsa):
    falsa = recepcion_falsa(
        ResultadoRecepcion(
            estado="procesado",
            registro=_registro(),
            resultados=[
                {
                    "codigo_legacy": "PRE-100",
                    "presupuesto_id": "p1",
                    "accion": "creado",
                    "renglones_procesados": 2,
                    "renglones_sin_producto": 0,
                }
            ],
        )
    )

    respuesta = _subir(_cliente_con_usuario("admin"), b"contenido crudo", "C:\\fakepath\\pres.csv")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "estado": "procesado",
        "registro_id": "reg-1",
        "nombre_archivo": "presupuestos.csv",
        "procesado_at": "2026-11-04T12:00:00Z",
        "errores": [],
        "resultados": [
            {
                "codigo_legacy": "PRE-100",
                "presupuesto_id": "p1",
                "accion": "creado",
                "renglones_procesados": 2,
                "renglones_sin_producto": 0,
            }
        ],
    }
    assert falsa.llamadas == [
        {
            "client": "service-client",
            "drogueria_id": "drog-1",
            "tipo": "presupuestos",
            "nombre_archivo": "pres.csv",
            "contenido": b"contenido crudo",
            "origen": "manual",
            "usuario_id": "user-1",
        }
    ]


def test_errores_de_parseo_vuelven_con_200_y_estado_error(recepcion_falsa):
    errores = [ErrorLinea(linea=2, mensaje="renglón no es un número entero")]
    recepcion_falsa(
        ResultadoRecepcion(
            estado="error",
            registro=_registro(estado="error", errores=errores, procesado_at=None, intentos=1),
            errores=errores,
        )
    )

    respuesta = _subir(_cliente_con_usuario("admin"))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "error"
    assert cuerpo["procesado_at"] is None
    assert cuerpo["errores"] == [{"linea": 2, "mensaje": "renglón no es un número entero"}]
    assert cuerpo["resultados"] == []


def test_duplicado_informa_la_fecha_del_procesamiento_original(recepcion_falsa):
    recepcion_falsa(ResultadoRecepcion(estado="duplicado", registro=_registro()))

    cuerpo = _subir(_cliente_con_usuario("admin")).json()

    assert cuerpo["estado"] == "duplicado"
    assert cuerpo["procesado_at"] == "2026-11-04T12:00:00Z"
    assert cuerpo["resultados"] == []


def test_error_de_dominio_en_la_entrega_conserva_status_y_mensaje(recepcion_falsa):
    recepcion_falsa(error=NotFoundError("No se encontró el cliente CLI-9"))

    respuesta = _subir(_cliente_con_usuario("admin"))

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "No se encontró el cliente CLI-9"}


@pytest.mark.parametrize("rol", ["superadmin", "gerencia", "compras", "lider_comercial", "comercial"])
def test_solo_admin_puede_subir_presupuestos(recepcion_falsa, rol):
    falsa = recepcion_falsa(ResultadoRecepcion(estado="duplicado", registro=_registro()))

    respuesta = _subir(_cliente_con_usuario(rol))

    assert respuesta.status_code == 403
    assert falsa.llamadas == []


def test_sin_archivo_es_422(recepcion_falsa):
    falsa = recepcion_falsa()

    respuesta = _cliente_con_usuario("admin").post(URL)

    assert respuesta.status_code == 422
    assert falsa.llamadas == []


def test_archivo_mas_grande_que_el_limite_es_413_y_no_se_procesa(recepcion_falsa):
    # R1-unbounded-upload-read: el archivo se leía entero a memoria sin tope.
    falsa = recepcion_falsa(ResultadoRecepcion(estado="duplicado", registro=_registro()))

    respuesta = _subir(
        _cliente_con_usuario("admin"), b"x" * (router_module.TAMANO_MAXIMO_BYTES + 1)
    )

    assert respuesta.status_code == 413
    assert respuesta.json() == {"detail": "El archivo supera el tamaño máximo de 10 MB"}
    assert falsa.llamadas == []


def test_archivo_del_tamano_limite_se_procesa(recepcion_falsa):
    falsa = recepcion_falsa(ResultadoRecepcion(estado="duplicado", registro=_registro()))
    contenido = b"x" * router_module.TAMANO_MAXIMO_BYTES

    respuesta = _subir(_cliente_con_usuario("admin"), contenido)

    assert router_module.TAMANO_MAXIMO_BYTES == 10 * 1024 * 1024
    assert respuesta.status_code == 200, respuesta.text
    assert [len(llamada["contenido"]) for llamada in falsa.llamadas] == [len(contenido)]


@pytest.mark.parametrize("metodo", ["subir", "listar"])
def test_usuario_sin_drogueria_es_403(recepcion_falsa, metodo):
    # R3-004: los dos endpoints exigen una droguería (un superadmin sin tenant no
    # puede subir ni listar; el listado no es multi-tenant).
    falsa = recepcion_falsa(ResultadoRecepcion(estado="duplicado", registro=_registro()))
    rol = "admin" if metodo == "subir" else "superadmin"
    cliente = _cliente_con_usuario(rol, drogueria_id=None)
    cliente.app.dependency_overrides[router_module.get_user_client] = lambda: "user-client"

    respuesta = (
        _subir(cliente) if metodo == "subir" else cliente.get("/integracion-progress/archivos")
    )

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "El usuario no tiene una droguería asignada"}
    assert falsa.llamadas == []


def test_listar_archivos_con_rol_sin_permiso_es_403():
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id="user-1", drogueria_id="drog-1", rol="cliente_externo"
    )

    respuesta = TestClient(app).get("/integracion-progress/archivos")

    assert respuesta.status_code == 403


# --- integración contra TEST ---------------------------------------------------


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
def test_carga_manual_de_punta_a_punta_duplicado_y_listado(
    service_client,
    seed_drogueria,
    seed_cliente_progress,
    crear_usuario_con_token,
    limpiar_progress_archivos,
):
    sufijo = seed_drogueria["id"][:8]
    codigo_cliente = f"CLI-IP-{sufijo}"
    numero = f"PRE-IP-{sufijo}"
    seed_cliente_progress(codigo_interno=codigo_cliente)
    usuario_id, token = crear_usuario_con_token(rol="admin", drogueria_id=seed_drogueria["id"])
    _, token_comercial = crear_usuario_con_token(
        rol="comercial", drogueria_id=seed_drogueria["id"]
    )
    contenido = "\n".join(
        [ENCABEZADO, f"{codigo_cliente};Hospital Pérez;{numero};1;Jarabe pediátrico;10,5"]
    ).encode("cp1252")
    client = TestClient(_app())

    primera = client.post(
        URL, files={"archivo": ("PRESUPUESTOS.csv", contenido, "text/csv")}, headers=_auth(token)
    )
    cuerpo = primera.json()
    try:
        assert primera.status_code == 200, primera.text
        assert cuerpo["estado"] == "procesado"
        assert cuerpo["errores"] == []
        assert [r["accion"] for r in cuerpo["resultados"]] == ["creado"]

        registro = (
            service_client.table("progress_archivos")
            .select("*")
            .eq("id", cuerpo["registro_id"])
            .execute()
            .data[0]
        )
        assert registro["estado"] == "procesado"
        assert registro["origen"] == "manual"
        assert registro["sentido"] == "entrada"
        assert registro["filas"] == 1
        assert registro["usuario_id"] == usuario_id

        segunda = client.post(
            URL, files={"archivo": ("otro.csv", contenido, "text/csv")}, headers=_auth(token)
        )
        assert segunda.status_code == 200
        assert segunda.json()["estado"] == "duplicado"
        assert segunda.json()["registro_id"] == cuerpo["registro_id"]
        assert segunda.json()["resultados"] == []

        # Listado con el user client: RLS deja leer a comercial su propio tenant.
        listado = client.get(
            "/integracion-progress/archivos?sentido=entrada&estado=procesado",
            headers=_auth(token_comercial),
        )
        assert listado.status_code == 200, listado.text
        assert [f["id"] for f in listado.json()] == [cuerpo["registro_id"]]
        vacio = client.get(
            "/integracion-progress/archivos?estado=error", headers=_auth(token_comercial)
        )
        assert vacio.json() == []
    finally:
        for resultado in cuerpo.get("resultados", []):
            presupuesto = (
                service_client.table("presupuestos")
                .select("id, proceso_comercial_id")
                .eq("id", resultado["presupuesto_id"])
                .execute()
                .data
            )
            if presupuesto:
                service_client.table("presupuestos").delete().eq(
                    "id", presupuesto[0]["id"]
                ).execute()
                service_client.table("procesos_comerciales").delete().eq(
                    "id", presupuesto[0]["proceso_comercial_id"]
                ).execute()


@pytest.mark.integration
def test_carga_manual_con_errores_no_importa_nada(
    service_client, seed_drogueria, crear_usuario_con_token, limpiar_progress_archivos
):
    _, token = crear_usuario_con_token(rol="admin", drogueria_id=seed_drogueria["id"])
    numero = f"PRE-IP-ERR-{seed_drogueria['id'][:8]}"
    contenido = "\n".join([ENCABEZADO, f"CLI-X;Hospital;{numero};abc;Jarabe;10"]).encode()

    respuesta = TestClient(_app()).post(
        URL, files={"archivo": ("err.csv", contenido, "text/csv")}, headers=_auth(token)
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "error"
    assert cuerpo["errores"] == [{"linea": 2, "mensaje": "renglón no es un número entero"}]
    registro = (
        service_client.table("progress_archivos")
        .select("estado, errores, intentos")
        .eq("id", cuerpo["registro_id"])
        .execute()
        .data[0]
    )
    assert registro == {
        "estado": "error",
        "errores": [{"linea": 2, "mensaje": "renglón no es un número entero"}],
        "intentos": 1,
    }
    mapa = (
        service_client.table("presupuesto_legacy_map")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", numero)
        .execute()
        .data
    )
    assert mapa == []
