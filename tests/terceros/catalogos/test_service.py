import uuid

import pytest

from services.shared.exceptions import NotFoundError
from services.terceros.catalogos.models import (
    CondicionPagoCreate,
    CondicionPagoUpdate,
    FormaPagoUpdate,
    SectorContactoUpdate,
)
from services.terceros.catalogos.service import (
    actualizar_condicion_pago,
    actualizar_forma_pago,
    actualizar_sector,
    crear_condicion_pago,
    listar_condiciones_pago,
    listar_formas_pago,
    listar_sectores,
    obtener_condicion_pago,
)


# ---------------------------------------------------------------------------
# 4.3 — scoping por drogueria_id
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_condicion_pago_de_otra_drogueria_no_aparece_en_el_listado(
    service_client, seed_drogueria, seed_condicion_pago_factory
):
    propia = seed_condicion_pago_factory()
    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{uuid.uuid4().int % 99_999_999:08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": f"otra-catalogos-{uuid.uuid4()}@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]
    ajena = service_client.table("condiciones_pago").insert(
        {"drogueria_id": otra_drogueria["id"], "nombre": f"Ajena {uuid.uuid4().hex[:8]}"}
    ).execute().data[0]

    try:
        listado = listar_condiciones_pago(
            service_client, drogueria_id=seed_drogueria["id"], activo=None
        )
        assert propia["id"] in {c["id"] for c in listado}
        assert ajena["id"] not in {c["id"] for c in listado}
    finally:
        service_client.table("condiciones_pago").delete().eq("id", ajena["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_obtener_condicion_pago_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_condicion_pago_factory
):
    condicion = seed_condicion_pago_factory()
    with pytest.raises(NotFoundError):
        obtener_condicion_pago(
            service_client, condicion_pago_id=condicion["id"], drogueria_id="otra-drogueria"
        )


# ---------------------------------------------------------------------------
# 4.4 — plazos_dias multi-término y de un solo término
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_condicion_pago_almacena_multiples_plazos(
    service_client, seed_drogueria, limpiar_terceros
):
    resultado = crear_condicion_pago(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=CondicionPagoCreate(nombre=f"30/60/90 {uuid.uuid4().hex[:8]}", plazos_dias=[30, 60, 90]),
    )
    assert resultado["plazos_dias"] == [30, 60, 90]


@pytest.mark.integration
def test_condicion_pago_almacena_un_solo_plazo(service_client, seed_drogueria, limpiar_terceros):
    resultado = crear_condicion_pago(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=CondicionPagoCreate(nombre=f"Contado {uuid.uuid4().hex[:8]}", plazos_dias=[30]),
    )
    assert resultado["plazos_dias"] == [30]


# ---------------------------------------------------------------------------
# 4.5 / 4.6 — D4: activo oculto por defecto, pero referenciable por FK
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_desactivar_forma_pago_la_oculta_del_listado_por_defecto_pero_sigue_existiendo(
    service_client, seed_drogueria, seed_forma_pago_factory
):
    forma = seed_forma_pago_factory(tipo="transferencia")

    actualizar_forma_pago(
        service_client,
        forma_pago_id=forma["id"],
        drogueria_id=seed_drogueria["id"],
        body=FormaPagoUpdate(activo=False),
    )

    por_defecto = listar_formas_pago(service_client, drogueria_id=seed_drogueria["id"])
    assert forma["id"] not in {f["id"] for f in por_defecto}

    todas = listar_formas_pago(service_client, drogueria_id=seed_drogueria["id"], activo=None)
    assert forma["id"] in {f["id"] for f in todas}

    fila = (
        service_client.table("formas_pago").select("id,activo").eq("id", forma["id"]).execute().data[0]
    )
    assert fila["activo"] is False


@pytest.mark.integration
def test_listar_sectores_oculta_inactivos_por_defecto(
    service_client, seed_drogueria, seed_sector_contacto_factory
):
    activo = seed_sector_contacto_factory()
    inactivo = seed_sector_contacto_factory()
    actualizar_sector(
        service_client,
        sector_id=inactivo["id"],
        drogueria_id=seed_drogueria["id"],
        body=SectorContactoUpdate(activo=False),
    )

    por_defecto = listar_sectores(service_client, drogueria_id=seed_drogueria["id"])
    assert {s["id"] for s in por_defecto} == {activo["id"]}


@pytest.mark.integration
def test_listar_condiciones_pago_oculta_inactivas_por_defecto(
    service_client, seed_drogueria, seed_condicion_pago_factory
):
    activa = seed_condicion_pago_factory()
    inactiva = seed_condicion_pago_factory()
    actualizar_condicion_pago(
        service_client,
        condicion_pago_id=inactiva["id"],
        drogueria_id=seed_drogueria["id"],
        body=CondicionPagoUpdate(activo=False),
    )

    por_defecto = listar_condiciones_pago(service_client, drogueria_id=seed_drogueria["id"])
    assert {c["id"] for c in por_defecto} == {activa["id"]}


# ---------------------------------------------------------------------------
# 4.7 — cross-tenant catalog access -> NotFoundError (D3)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_actualizar_condicion_pago_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_condicion_pago_factory
):
    condicion = seed_condicion_pago_factory()
    with pytest.raises(NotFoundError):
        actualizar_condicion_pago(
            service_client,
            condicion_pago_id=condicion["id"],
            drogueria_id="otra-drogueria",
            body=CondicionPagoUpdate(descripcion="hackeado"),
        )
