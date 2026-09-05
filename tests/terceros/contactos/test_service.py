import uuid

import pytest

from services.shared.exceptions import NotFoundError, ValidationError
from services.terceros.contactos.models import TerceroContactoCreate, TerceroContactoUpdate
from services.terceros.contactos.service import (
    actualizar_contacto,
    crear_contacto,
    listar_contactos,
    obtener_contacto,
)
from services.terceros.identidad.models import ProveedorRolCreate
from services.terceros.identidad.service import asignar_rol_proveedor


# ---------------------------------------------------------------------------
# 6.3 — contacto para un tercero con solo rol proveedor
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_contacto_para_tercero_solo_con_rol_proveedor(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    asignar_rol_proveedor(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProveedorRolCreate(tipo="laboratorio"),
    )

    creado = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="Ana"),
    )

    encontrado = obtener_contacto(
        service_client, contacto_id=creado["id"], drogueria_id=seed_drogueria["id"]
    )
    assert encontrado["tercero_id"] == tercero["id"]


# ---------------------------------------------------------------------------
# 6.4 / 6.5 — campos completos y sector opcional
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_contacto_completo_almacena_todos_los_campos_y_activo_por_defecto(
    service_client, seed_drogueria, seed_tercero_factory, seed_sector_contacto_factory
):
    tercero = seed_tercero_factory()
    sector = seed_sector_contacto_factory()

    creado = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(
            nombre="Ana",
            apellido="Pérez",
            sector_id=sector["id"],
            cargo="Compras",
            email="ana@example.com",
            telefono="341-1111111",
            celular="341-2222222",
        ),
    )

    assert creado["nombre"] == "Ana"
    assert creado["apellido"] == "Pérez"
    assert creado["sector_id"] == sector["id"]
    assert creado["cargo"] == "Compras"
    assert creado["email"] == "ana@example.com"
    assert creado["telefono"] == "341-1111111"
    assert creado["celular"] == "341-2222222"
    assert creado["activo"] is True


@pytest.mark.integration
def test_crear_contacto_sin_sector_queda_con_sector_nulo(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()

    creado = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="Ana"),
    )

    assert creado["sector_id"] is None


# ---------------------------------------------------------------------------
# 6.6 — sector de otra droguería
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_contacto_con_sector_de_otra_drogueria_lanza_validation(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{uuid.uuid4().int % 99_999_999:08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": f"otra-contactos-{uuid.uuid4()}@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]
    sector_ajeno = service_client.table("sectores_contacto").insert(
        {"drogueria_id": otra_drogueria["id"], "nombre": f"Ajeno {uuid.uuid4().hex[:8]}"}
    ).execute().data[0]

    try:
        with pytest.raises(ValidationError):
            crear_contacto(
                service_client,
                tercero_id=tercero["id"],
                drogueria_id=seed_drogueria["id"],
                body=TerceroContactoCreate(nombre="Ana", sector_id=sector_ajeno["id"]),
            )
    finally:
        service_client.table("sectores_contacto").delete().eq("id", sector_ajeno["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


# ---------------------------------------------------------------------------
# 6.7 / 6.8 — contacto principal único activo
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_nuevo_contacto_principal_demueve_al_anterior(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    c1 = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="Uno", es_principal=True),
    )

    c2 = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="Dos", es_principal=True),
    )

    c1_actualizado = obtener_contacto(
        service_client, contacto_id=c1["id"], drogueria_id=seed_drogueria["id"]
    )
    assert c1_actualizado["es_principal"] is False
    assert c2["es_principal"] is True

    principales = [
        c
        for c in listar_contactos(service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"])
        if c["es_principal"]
    ]
    assert len(principales) == 1
    assert principales[0]["id"] == c2["id"]


@pytest.mark.integration
def test_desactivar_contacto_principal_no_promueve_a_otro(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    c1 = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="Uno", es_principal=True),
    )
    c2 = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="Dos", es_principal=False),
    )

    actualizar_contacto(
        service_client,
        contacto_id=c1["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoUpdate(activo=False),
    )

    c1_actualizado = obtener_contacto(
        service_client, contacto_id=c1["id"], drogueria_id=seed_drogueria["id"]
    )
    c2_actualizado = obtener_contacto(
        service_client, contacto_id=c2["id"], drogueria_id=seed_drogueria["id"]
    )
    assert c1_actualizado["activo"] is False
    assert c2_actualizado["es_principal"] is False


# ---------------------------------------------------------------------------
# 6.9 — D4: baja lógica oculta del listado por defecto
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_desactivar_contacto_lo_oculta_del_listado_por_defecto(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    activo = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="Activo"),
    )
    a_desactivar = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="A desactivar"),
    )

    actualizar_contacto(
        service_client,
        contacto_id=a_desactivar["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoUpdate(activo=False),
    )

    por_defecto = listar_contactos(service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"])
    assert {c["id"] for c in por_defecto} == {activo["id"]}

    todos = listar_contactos(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"], activo=None
    )
    assert {c["id"] for c in todos} == {activo["id"], a_desactivar["id"]}


# ---------------------------------------------------------------------------
# 6.10 — aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_obtener_contacto_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    contacto = crear_contacto(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroContactoCreate(nombre="Ana"),
    )

    with pytest.raises(NotFoundError):
        obtener_contacto(service_client, contacto_id=contacto["id"], drogueria_id="otra-drogueria")
