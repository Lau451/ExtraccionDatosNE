import secrets

import pytest

from services.presupuestacion.comparativas.repository import listar_renglones_ganados
from services.presupuestacion.comparativas.service import asignar_proveedor
from services.presupuestacion.core.exceptions import NotFoundError, ValidationError


@pytest.mark.integration
def test_asignar_proveedor_actualiza_la_oferta(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_comparativa_factory,
    seed_oferta_item_factory,
    seed_proveedor,
):
    comparativa = seed_comparativa_factory(seed_proceso_comercial["id"])
    oferta = seed_oferta_item_factory(comparativa["id"], proveedor="Texto crudo de Gemini")

    resultado = asignar_proveedor(
        service_client, oferta_item_id=oferta["id"], proveedor_id=seed_proveedor["id"]
    )

    assert resultado["proveedor_id"] == seed_proveedor["id"]
    fila = (
        service_client.table("ofertas_items")
        .select("proveedor_id")
        .eq("id", oferta["id"])
        .execute()
        .data[0]
    )
    assert fila["proveedor_id"] == seed_proveedor["id"]


@pytest.mark.integration
def test_asignar_proveedor_oferta_inexistente(service_client, seed_proveedor):
    with pytest.raises(NotFoundError):
        asignar_proveedor(
            service_client,
            oferta_item_id="00000000-0000-0000-0000-000000000000",
            proveedor_id=seed_proveedor["id"],
        )


@pytest.mark.integration
def test_asignar_proveedor_proveedor_inexistente(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_comparativa_factory,
    seed_oferta_item_factory,
):
    comparativa = seed_comparativa_factory(seed_proceso_comercial["id"])
    oferta = seed_oferta_item_factory(comparativa["id"])

    with pytest.raises(NotFoundError):
        asignar_proveedor(
            service_client,
            oferta_item_id=oferta["id"],
            proveedor_id="00000000-0000-0000-0000-000000000000",
        )


@pytest.mark.integration
def test_asignar_proveedor_de_otra_drogueria_falla(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_comparativa_factory,
    seed_oferta_item_factory,
):
    comparativa = seed_comparativa_factory(seed_proceso_comercial["id"])
    oferta = seed_oferta_item_factory(comparativa["id"])

    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": "otra-comp@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]
    otro_proveedor = service_client.table("proveedores").insert(
        {"drogueria_id": otra_drogueria["id"], "razon_social": "Proveedor de otra droguería"}
    ).execute().data[0]

    try:
        with pytest.raises(ValidationError):
            asignar_proveedor(
                service_client, oferta_item_id=oferta["id"], proveedor_id=otro_proveedor["id"]
            )
    finally:
        service_client.table("proveedores").delete().eq("id", otro_proveedor["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_v_renglones_ganados_muestra_ofertas_propias_ganadoras(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_comparativa_factory,
    seed_oferta_item_factory,
):
    comparativa = seed_comparativa_factory(seed_proceso_comercial["id"])
    ganadora_estimada = seed_oferta_item_factory(
        comparativa["id"],
        renglon_id="1",
        es_drogueria_propia=True,
        adjudicacion_estimada=True,
        precio_unitario="9.00",
    )
    # No propia: no debe aparecer aunque gane.
    seed_oferta_item_factory(
        comparativa["id"], renglon_id="2", es_drogueria_propia=False, adjudicacion_estimada=True
    )
    # Propia pero no ganadora: tampoco debe aparecer.
    seed_oferta_item_factory(
        comparativa["id"], renglon_id="3", es_drogueria_propia=True, adjudicacion_estimada=False
    )

    renglones = listar_renglones_ganados(
        service_client, proceso_comercial_id=seed_proceso_comercial["id"]
    )

    ids_ganados = {r["oferta_item_id"] for r in renglones}
    assert ganadora_estimada["id"] in ids_ganados
    assert len(renglones) == 1
    assert renglones[0]["nivel"] == "estimado"
