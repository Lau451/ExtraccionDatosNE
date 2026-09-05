import uuid

import pytest

from services.shared.exceptions import ConflictError, NotFoundError
from services.terceros.direcciones.models import DireccionUsoCreate, TerceroDireccionCreate, TerceroDireccionUpdate
from services.terceros.direcciones.service import (
    actualizar_direccion,
    asignar_uso,
    crear_direccion,
    eliminar_direccion,
    eliminar_uso,
    listar_direcciones,
    listar_usos,
    obtener_direccion,
)


# ---------------------------------------------------------------------------
# 5.3 / 5.4 — creación y scoping
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_direccion_para_tercero_existente(service_client, seed_drogueria, seed_tercero_factory):
    tercero = seed_tercero_factory()

    resultado = crear_direccion(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroDireccionCreate(calle="San Martín 1234", ciudad="Rosario"),
    )

    assert resultado["tercero_id"] == tercero["id"]
    assert resultado["drogueria_id"] == seed_drogueria["id"]
    assert resultado["calle"] == "San Martín 1234"


@pytest.mark.integration
def test_crear_direccion_para_tercero_inexistente_lanza_not_found(
    service_client, seed_drogueria, limpiar_terceros
):
    with pytest.raises(NotFoundError):
        crear_direccion(
            service_client,
            tercero_id=str(uuid.uuid4()),
            drogueria_id=seed_drogueria["id"],
            body=TerceroDireccionCreate(calle="Calle inexistente"),
        )


# ---------------------------------------------------------------------------
# 5.5 / 5.6 / 5.7 — usos N:M
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_asignar_dos_usos_simultaneos_a_la_misma_direccion(
    service_client, seed_drogueria, seed_direccion_factory
):
    direccion = seed_direccion_factory()

    asignar_uso(
        service_client,
        direccion_id=direccion["id"],
        tercero_id=direccion["tercero_id"],
        drogueria_id=seed_drogueria["id"],
        body=DireccionUsoCreate(uso="facturacion"),
    )
    asignar_uso(
        service_client,
        direccion_id=direccion["id"],
        tercero_id=direccion["tercero_id"],
        drogueria_id=seed_drogueria["id"],
        body=DireccionUsoCreate(uso="entrega"),
    )

    usos = listar_usos(service_client, direccion_id=direccion["id"], drogueria_id=seed_drogueria["id"])
    assert {u["uso"] for u in usos} == {"facturacion", "entrega"}


@pytest.mark.integration
def test_remover_un_uso_no_afecta_al_otro(service_client, seed_drogueria, seed_direccion_factory):
    direccion = seed_direccion_factory()
    for uso in ("facturacion", "entrega"):
        asignar_uso(
            service_client,
            direccion_id=direccion["id"],
            tercero_id=direccion["tercero_id"],
            drogueria_id=seed_drogueria["id"],
            body=DireccionUsoCreate(uso=uso),
        )

    eliminar_uso(
        service_client, direccion_id=direccion["id"], drogueria_id=seed_drogueria["id"], uso="entrega"
    )

    usos = listar_usos(service_client, direccion_id=direccion["id"], drogueria_id=seed_drogueria["id"])
    assert {u["uso"] for u in usos} == {"facturacion"}

    filtradas_por_entrega = listar_direcciones(
        service_client,
        tercero_id=direccion["tercero_id"],
        drogueria_id=seed_drogueria["id"],
        uso="entrega",
    )
    assert direccion["id"] not in {d["id"] for d in filtradas_por_entrega}


@pytest.mark.integration
def test_filtrar_direcciones_por_uso(service_client, seed_drogueria, seed_tercero_factory, seed_direccion_factory):
    tercero = seed_tercero_factory()
    con_uso = seed_direccion_factory(tercero_id=tercero["id"], calle="Con uso 1")
    sin_uso = seed_direccion_factory(tercero_id=tercero["id"], calle="Sin uso 1")
    asignar_uso(
        service_client,
        direccion_id=con_uso["id"],
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=DireccionUsoCreate(uso="documentacion"),
    )

    resultado = listar_direcciones(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"], uso="documentacion"
    )

    ids = {d["id"] for d in resultado}
    assert con_uso["id"] in ids
    assert sin_uso["id"] not in ids


@pytest.mark.integration
def test_asignar_segunda_direccion_principal_mismo_uso_lanza_conflict(
    service_client, seed_drogueria, seed_tercero_factory, seed_direccion_factory
):
    tercero = seed_tercero_factory()
    direccion_1 = seed_direccion_factory(tercero_id=tercero["id"], calle="Principal actual")
    direccion_2 = seed_direccion_factory(tercero_id=tercero["id"], calle="Aspira a ser principal")
    asignar_uso(
        service_client,
        direccion_id=direccion_1["id"],
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=DireccionUsoCreate(uso="facturacion", es_principal=True),
    )

    with pytest.raises(ConflictError):
        asignar_uso(
            service_client,
            direccion_id=direccion_2["id"],
            tercero_id=tercero["id"],
            drogueria_id=seed_drogueria["id"],
            body=DireccionUsoCreate(uso="facturacion", es_principal=True),
        )


# ---------------------------------------------------------------------------
# 5.8 / 5.9 — edición y baja
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_editar_campos_de_direccion_no_cambia_sus_usos(
    service_client, seed_drogueria, seed_direccion_factory
):
    direccion = seed_direccion_factory(calle="Calle vieja")
    asignar_uso(
        service_client,
        direccion_id=direccion["id"],
        tercero_id=direccion["tercero_id"],
        drogueria_id=seed_drogueria["id"],
        body=DireccionUsoCreate(uso="facturacion"),
    )

    actualizado = actualizar_direccion(
        service_client,
        direccion_id=direccion["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroDireccionUpdate(calle="Calle nueva", ciudad="Rosario"),
    )

    assert actualizado["calle"] == "Calle nueva"
    assert actualizado["ciudad"] == "Rosario"

    usos = listar_usos(service_client, direccion_id=direccion["id"], drogueria_id=seed_drogueria["id"])
    assert {u["uso"] for u in usos} == {"facturacion"}


@pytest.mark.integration
def test_eliminar_direccion_remueve_sus_usos_sin_borrar_el_tercero(
    service_client, seed_drogueria, seed_tercero_factory, seed_direccion_factory
):
    tercero = seed_tercero_factory()
    direccion_a = seed_direccion_factory(tercero_id=tercero["id"], calle="A eliminar")
    direccion_b = seed_direccion_factory(tercero_id=tercero["id"], calle="Sobrevive")
    asignar_uso(
        service_client,
        direccion_id=direccion_a["id"],
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=DireccionUsoCreate(uso="facturacion"),
    )

    eliminar_direccion(service_client, direccion_id=direccion_a["id"], drogueria_id=seed_drogueria["id"])

    with pytest.raises(NotFoundError):
        obtener_direccion(service_client, direccion_id=direccion_a["id"], drogueria_id=seed_drogueria["id"])
    usos_restantes = (
        service_client.table("direccion_usos").select("id").eq("direccion_id", direccion_a["id"]).execute().data
    )
    assert usos_restantes == []

    sobreviviente = obtener_direccion(
        service_client, direccion_id=direccion_b["id"], drogueria_id=seed_drogueria["id"]
    )
    assert sobreviviente["id"] == direccion_b["id"]
    tercero_vivo = (
        service_client.table("terceros").select("id").eq("id", tercero["id"]).execute().data
    )
    assert len(tercero_vivo) == 1


# ---------------------------------------------------------------------------
# 5.10 — aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_obtener_direccion_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_direccion_factory
):
    direccion = seed_direccion_factory()
    with pytest.raises(NotFoundError):
        obtener_direccion(service_client, direccion_id=direccion["id"], drogueria_id="otra-drogueria")
