"""presupuestador-v1 T2b (S2, S8): validating a licitación or a directa starts
its proceso comercial. The user picks the class, the cliente (required) and,
for a licitación, its name; the proceso is named "<cliente> - <nombre>" for a
licitación and "<cliente> - <n>" (ascending per cliente) for a directa."""

import secrets

import pytest

from services.presupuestacion.core.exceptions import ConflictError, ValidationError
from services.presupuestacion.extraccion.models import NuevoProcesoIn
from services.presupuestacion.extraccion.service import validar_extraccion

FILAS = [
    {"item": "1", "cantidad": "10", "descripcion": "Ibuprofeno 600mg x30", "origen": "pliego"},
    {"item": "2", "cantidad": "5", "descripcion": "Gasa estéril x10", "origen": "pliego"},
]
COLUMNAS = ["item", "cantidad", "descripcion", "origen"]


@pytest.fixture
def procesos_por_cliente(service_client, seed_cliente_factory, seed_extraction_result_factory):
    """Deletes every proceso comercial of the registered clientes after the test
    (the ones validation creates plus any seeded here). Torn down before the
    extraction and cliente factories, so it unlinks what still references them."""
    clientes: list[str] = []

    def _procesos(cliente_id: str) -> list[dict]:
        return (
            service_client.table("procesos_comerciales")
            .select("*")
            .eq("cliente_id", cliente_id)
            .order("created_at")
            .execute()
            .data
        )

    def _registrar(cliente_id: str):
        clientes.append(cliente_id)
        return lambda: _procesos(cliente_id)

    yield _registrar

    for cliente_id in clientes:
        for proceso in _procesos(cliente_id):
            items = (
                service_client.table("items_proceso")
                .select("id")
                .eq("proceso_comercial_id", proceso["id"])
                .execute()
                .data
            )
            for item in items:
                service_client.table("matching_candidatos").delete().eq(
                    "item_proceso_id", item["id"]
                ).execute()
                service_client.table("items_proceso").update({"alias_id": None}).eq(
                    "id", item["id"]
                ).execute()
            for item in items:
                service_client.table("items_proceso").delete().eq("id", item["id"]).execute()
            service_client.table("extraction_results").update(
                {"proceso_comercial_id": None}
            ).eq("proceso_comercial_id", proceso["id"]).execute()
            service_client.table("historial_cambios").delete().eq(
                "proceso_comercial_id", proceso["id"]
            ).execute()
            service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()


def _extraccion(service_client, extraction_id: str) -> dict:
    return (
        service_client.table("extraction_results")
        .select("validado, proceso_comercial_id, document_type")
        .eq("id", extraction_id)
        .execute()
        .data[0]
    )


@pytest.mark.integration
def test_validar_licitacion_crea_el_proceso_con_cliente_y_nombre(
    service_client, seed_drogueria, seed_cliente_factory, seed_extraction_result_factory,
    seed_usuario_sistema, procesos_por_cliente,
):
    cliente = seed_cliente_factory("Hospital Sayago")
    procesos = procesos_por_cliente(cliente["cliente_id"])
    extraction = seed_extraction_result_factory("licitacion", filas=FILAS, columnas=COLUMNAS)

    resultado = validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=None,
        nuevo_proceso=NuevoProcesoIn(
            clase="licitacion", cliente_id=cliente["cliente_id"], nombre_licitacion="  LIC 14/2026  "
        ),
    )

    [proceso] = procesos()
    assert proceso["nombre"] == "Hospital Sayago - LIC 14/2026"
    assert proceso["clase"] == "licitacion"
    assert proceso["cliente_id"] == cliente["cliente_id"]
    assert proceso["drogueria_id"] == seed_drogueria["id"]
    assert proceso["created_by"] == seed_usuario_sistema["id"]
    assert resultado.proceso_comercial_id == proceso["id"]
    assert resultado.document_type == "licitacion"
    assert resultado.filas_creadas == 2
    items = (
        service_client.table("items_proceso")
        .select("numero_renglon, descripcion")
        .eq("proceso_comercial_id", proceso["id"])
        .order("numero_renglon")
        .execute()
        .data
    )
    assert [item["descripcion"] for item in items] == ["Ibuprofeno 600mg x30", "Gasa estéril x10"]
    assert _extraccion(service_client, extraction["id"]) == {
        "validado": True,
        "proceso_comercial_id": proceso["id"],
        "document_type": "licitacion",
    }


@pytest.mark.integration
def test_validar_directa_numera_el_proceso_por_cliente(
    service_client, seed_drogueria, seed_cliente_factory, seed_extraction_result_factory,
    seed_usuario_sistema, procesos_por_cliente,
):
    cliente = seed_cliente_factory("Hospital Sayago")
    otro_cliente = seed_cliente_factory("Clínica Norte")
    procesos = procesos_por_cliente(cliente["cliente_id"])
    procesos_por_cliente(otro_cliente["cliente_id"])
    for cliente_id, clase, nombre in (
        (cliente["cliente_id"], "cotizacion", "Hospital Sayago - 1"),
        (cliente["cliente_id"], "licitacion", "Hospital Sayago - LIC 1/2026"),
        (otro_cliente["cliente_id"], "cotizacion", "Clínica Norte - 1"),
        (otro_cliente["cliente_id"], "cotizacion", "Clínica Norte - 2"),
    ):
        service_client.table("procesos_comerciales").insert(
            {"drogueria_id": seed_drogueria["id"], "cliente_id": cliente_id, "clase": clase, "nombre": nombre}
        ).execute()
    extraction = seed_extraction_result_factory("licitacion", filas=FILAS, columnas=COLUMNAS)

    resultado = validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=None,
        nuevo_proceso=NuevoProcesoIn(clase="cotizacion", cliente_id=cliente["cliente_id"]),
    )

    nuevo = procesos()[-1]
    assert nuevo["nombre"] == "Hospital Sayago - 2"
    assert nuevo["clase"] == "cotizacion"
    assert nuevo["cliente_id"] == cliente["cliente_id"]
    assert resultado.proceso_comercial_id == nuevo["id"]
    assert resultado.document_type == "cotizacion"
    assert resultado.filas_creadas == 2
    assert _extraccion(service_client, extraction["id"]) == {
        "validado": True,
        "proceso_comercial_id": nuevo["id"],
        "document_type": "cotizacion",
    }


@pytest.mark.integration
@pytest.mark.parametrize("nombre_licitacion", [None, "", "   "])
def test_validar_licitacion_sin_nombre_no_crea_nada(
    service_client, seed_cliente_factory, seed_extraction_result_factory, seed_usuario_sistema,
    procesos_por_cliente, nombre_licitacion,
):
    cliente = seed_cliente_factory("Hospital Sayago")
    procesos = procesos_por_cliente(cliente["cliente_id"])
    extraction = seed_extraction_result_factory("licitacion", filas=FILAS, columnas=COLUMNAS)

    with pytest.raises(ValidationError, match="^Falta el nombre de la licitación$"):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=None,
            nuevo_proceso=NuevoProcesoIn(
                clase="licitacion", cliente_id=cliente["cliente_id"], nombre_licitacion=nombre_licitacion
            ),
        )

    assert procesos() == []
    assert _extraccion(service_client, extraction["id"]) == {
        "validado": False,
        "proceso_comercial_id": None,
        "document_type": "licitacion",
    }


@pytest.fixture
def otra_drogueria(service_client):
    """Requested before `seed_cliente_factory` so it is torn down after the
    cliente seeded in it."""
    drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": "otra@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]
    yield drogueria
    service_client.table("droguerias").delete().eq("id", drogueria["id"]).execute()


@pytest.mark.integration
def test_validar_con_cliente_de_otra_drogueria_no_crea_nada(
    service_client, otra_drogueria, seed_cliente_factory, seed_extraction_result_factory,
    seed_usuario_sistema, procesos_por_cliente,
):
    ajeno = seed_cliente_factory("Cliente ajeno", drogueria_id=otra_drogueria["id"])
    procesos = procesos_por_cliente(ajeno["cliente_id"])
    extraction = seed_extraction_result_factory("licitacion", filas=FILAS, columnas=COLUMNAS)

    with pytest.raises(
        ValidationError, match="^El cliente indicado no existe o no pertenece a esta droguería$"
    ):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=None,
            nuevo_proceso=NuevoProcesoIn(clase="cotizacion", cliente_id=ajeno["cliente_id"]),
        )

    assert procesos() == []
    assert _extraccion(service_client, extraction["id"]) == {
        "validado": False,
        "proceso_comercial_id": None,
        "document_type": "licitacion",
    }


@pytest.mark.integration
def test_validar_con_proceso_existente_y_nuevo_a_la_vez_no_crea_nada(
    service_client, seed_proceso_comercial, seed_cliente_factory, seed_extraction_result_factory,
    seed_usuario_sistema, procesos_por_cliente,
):
    cliente = seed_cliente_factory("Hospital Sayago")
    procesos = procesos_por_cliente(cliente["cliente_id"])
    extraction = seed_extraction_result_factory("licitacion", filas=FILAS, columnas=COLUMNAS)

    with pytest.raises(
        ValidationError,
        match="^Indicá un proceso comercial existente o los datos del nuevo, no ambos$",
    ):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=seed_proceso_comercial["id"],
            nuevo_proceso=NuevoProcesoIn(clase="cotizacion", cliente_id=cliente["cliente_id"]),
        )

    assert procesos() == []
    assert _extraccion(service_client, extraction["id"]) == {
        "validado": False,
        "proceso_comercial_id": None,
        "document_type": "licitacion",
    }


@pytest.mark.integration
def test_validar_comparativa_no_acepta_un_proceso_nuevo(
    service_client, seed_cliente_factory, seed_extraction_result_factory, seed_usuario_sistema,
    procesos_por_cliente,
):
    cliente = seed_cliente_factory("Hospital Sayago")
    procesos = procesos_por_cliente(cliente["cliente_id"])
    extraction = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "X", "precio_unitario": "10"}],
        columnas=["renglon", "proveedor", "precio_unitario"],
    )

    with pytest.raises(
        ValidationError,
        match="^Solo una licitación o una directa crea su proceso comercial al validarse$",
    ):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=None,
            nuevo_proceso=NuevoProcesoIn(clase="cotizacion", cliente_id=cliente["cliente_id"]),
        )

    assert procesos() == []
    assert _extraccion(service_client, extraction["id"])["validado"] is False


@pytest.mark.integration
def test_validar_extraccion_ya_vinculada_no_crea_otro_proceso(
    service_client, seed_proceso_comercial, seed_cliente_factory, seed_extraction_result_factory,
    seed_usuario_sistema, procesos_por_cliente,
):
    cliente = seed_cliente_factory("Hospital Sayago")
    procesos = procesos_por_cliente(cliente["cliente_id"])
    extraction = seed_extraction_result_factory(
        "licitacion", filas=FILAS, columnas=COLUMNAS,
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    with pytest.raises(
        ConflictError, match="^Esta extracción ya está vinculada a un proceso comercial$"
    ):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=None,
            nuevo_proceso=NuevoProcesoIn(clase="cotizacion", cliente_id=cliente["cliente_id"]),
        )

    assert procesos() == []
    assert _extraccion(service_client, extraction["id"]) == {
        "validado": False,
        "proceso_comercial_id": seed_proceso_comercial["id"],
        "document_type": "licitacion",
    }


def test_endpoint_pasa_el_proceso_nuevo_al_servicio(monkeypatch):
    from services.presupuestacion.core.auth import UsuarioPerfil
    from services.presupuestacion.extraccion import router
    from services.presupuestacion.extraccion.models import ValidarExtraccionRequest

    llamadas: list[dict] = []
    monkeypatch.setattr(router, "_verificar_pertenencia", lambda *a, **k: {})
    monkeypatch.setattr(
        router, "validar_extraccion_para_endpoint", lambda **kwargs: llamadas.append(kwargs)
    )

    router.validar_extraccion_endpoint(
        "extraccion-1",
        ValidarExtraccionRequest.model_validate(
            {"nuevo_proceso": {"clase": "licitacion", "cliente_id": "cli-1", "nombre_licitacion": "LIC 1"}}
        ),
        usuario=UsuarioPerfil(id="usuario-1", drogueria_id="drog-1", rol="comercial"),
        user_client=None,
    )

    assert llamadas[0]["proceso_comercial_id"] is None
    assert llamadas[0]["nuevo_proceso"] == NuevoProcesoIn(
        clase="licitacion", cliente_id="cli-1", nombre_licitacion="LIC 1"
    )


@pytest.mark.parametrize(
    "nuevo_proceso",
    [
        {"clase": "licitacion", "nombre_licitacion": "LIC 1"},  # sin cliente
        {"clase": "comparativa", "cliente_id": "cli-1"},  # clase inexistente
        {"clase": "cotizacion", "cliente_id": "cli-1", "extra": "x"},  # campo desconocido
    ],
)
def test_el_body_rechaza_un_proceso_nuevo_invalido(nuevo_proceso):
    from pydantic import ValidationError as PydanticValidationError

    from services.presupuestacion.extraccion.models import ValidarExtraccionRequest

    with pytest.raises(PydanticValidationError):
        ValidarExtraccionRequest.model_validate({"nuevo_proceso": nuevo_proceso})


@pytest.mark.integration
def test_reintento_tras_una_falla_reusa_el_proceso_ya_vinculado(
    service_client, seed_drogueria, seed_cliente_factory, seed_extraction_result_factory,
    seed_usuario_sistema, procesos_por_cliente,
):
    """A failure after the proceso was created leaves the extraction linked but
    not validated; confirming again with the same cliente and class reuses that
    proceso instead of answering a conflict (verify finding on fcfbd42)."""
    cliente = seed_cliente_factory("Hospital Sayago")
    procesos = procesos_por_cliente(cliente["cliente_id"])
    previo = service_client.table("procesos_comerciales").insert(
        {
            "drogueria_id": seed_drogueria["id"],
            "cliente_id": cliente["cliente_id"],
            "clase": "licitacion",
            "nombre": "Hospital Sayago - LIC 14/2026",
        }
    ).execute().data[0]
    extraction = seed_extraction_result_factory(
        "licitacion", filas=FILAS, columnas=COLUMNAS, proceso_comercial_id=previo["id"]
    )

    resultado = validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=None,
        nuevo_proceso=NuevoProcesoIn(
            clase="licitacion", cliente_id=cliente["cliente_id"], nombre_licitacion="LIC 14/2026"
        ),
    )

    assert [proceso["id"] for proceso in procesos()] == [previo["id"]]
    assert resultado.proceso_comercial_id == previo["id"]
    assert resultado.filas_creadas == 2
    assert _extraccion(service_client, extraction["id"]) == {
        "validado": True,
        "proceso_comercial_id": previo["id"],
        "document_type": "licitacion",
    }


@pytest.mark.integration
def test_renglones_repetidos_se_rechazan_antes_de_crear_el_proceso(
    service_client, seed_cliente_factory, seed_extraction_result_factory, seed_usuario_sistema,
    procesos_por_cliente,
):
    cliente = seed_cliente_factory("Hospital Sayago")
    procesos = procesos_por_cliente(cliente["cliente_id"])
    extraction = seed_extraction_result_factory("licitacion", filas=FILAS, columnas=COLUMNAS)

    with pytest.raises(ValidationError, match="^El renglón 1 está repetido$"):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=None,
            filas_override=[
                {"item": "1", "cantidad": "10", "descripcion": "Ibuprofeno 600mg x30"},
                {"item": " 1", "cantidad": "5", "descripcion": "Gasa estéril x10"},
            ],
            nuevo_proceso=NuevoProcesoIn(clase="cotizacion", cliente_id=cliente["cliente_id"]),
        )

    assert procesos() == []
    assert _extraccion(service_client, extraction["id"]) == {
        "validado": False,
        "proceso_comercial_id": None,
        "document_type": "licitacion",
    }


def test_orden_compra_no_acepta_un_proceso_nuevo(monkeypatch):
    from unittest.mock import MagicMock

    from services.presupuestacion.extraccion import repository as repo

    monkeypatch.setattr(
        repo,
        "buscar_extraction_result",
        lambda client, *, extraction_id: {
            "id": extraction_id,
            "drogueria_id": "drog-1",
            "document_type": "orden_compra",
            "status": "completed",
            "validado": False,
        },
    )
    client = MagicMock()

    with pytest.raises(
        ValidationError,
        match="^Solo una licitación o una directa crea su proceso comercial al validarse$",
    ):
        validar_extraccion(
            client,
            extraction_id="oc-1",
            usuario_id="usuario-1",
            proceso_comercial_id=None,
            nuevo_proceso=NuevoProcesoIn(clase="cotizacion", cliente_id="cli-1"),
        )

    client.table.assert_not_called()
