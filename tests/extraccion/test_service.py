import secrets
from decimal import Decimal

import pytest

from presupuestacion.core.exceptions import ConflictError, NotFoundError, ValidationError
from presupuestacion.extraccion.service import validar_extraccion


@pytest.mark.integration
def test_validar_licitacion_crea_items_proceso(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[
            {"item": "1", "cantidad": "10", "descripcion": "Ibuprofeno 600mg x30", "origen": "pliego"},
            {"item": "2", "cantidad": "5", "descripcion": "Gasa estéril x10", "origen": "pliego"},
        ],
        columnas=["item", "cantidad", "descripcion", "origen"],
    )

    resultado = validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    assert resultado.filas_creadas == 2
    assert resultado.document_type == "licitacion"

    items = (
        service_client.table("items_proceso")
        .select("*")
        .eq("proceso_comercial_id", seed_proceso_comercial["id"])
        .order("numero_renglon")
        .execute()
        .data
    )
    assert len(items) == 2
    assert items[0]["numero_renglon"] == 1
    assert items[0]["descripcion"] == "Ibuprofeno 600mg x30"
    assert items[0]["descripcion_normalizada"] == "IBUPROFENO 600MG X30"
    assert Decimal(str(items[0]["cantidad"])) == Decimal("10")
    assert items[0]["estado_matching"] in ("pendiente", "sugerido", "automatico")

    extraction_final = (
        service_client.table("extraction_results")
        .select("validado, validado_por, validado_at, proceso_comercial_id")
        .eq("id", extraction["id"])
        .execute()
        .data[0]
    )
    assert extraction_final["validado"] is True
    assert extraction_final["validado_por"] == seed_usuario_sistema["id"]
    assert extraction_final["proceso_comercial_id"] == seed_proceso_comercial["id"]


@pytest.mark.integration
def test_validar_ya_validada_levanta_conflict(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
    )
    validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    with pytest.raises(ConflictError):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=seed_proceso_comercial["id"],
        )


@pytest.mark.integration
def test_validar_sin_proceso_comercial_id_exige_indicarlo(
    service_client, seed_drogueria, seed_extraction_result_factory, seed_usuario_sistema
):
    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
    )

    with pytest.raises(ValidationError):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=None,
        )


@pytest.mark.integration
def test_validar_con_proceso_comercial_id_de_otra_drogueria_falla(
    service_client, seed_drogueria, seed_extraction_result_factory, seed_usuario_sistema
):
    otra_drogueria = service_client.table("droguerias").insert(
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
    otro_proceso = service_client.table("procesos_comerciales").insert(
        {"drogueria_id": otra_drogueria["id"], "clase": "cotizacion", "nombre": "Proceso de otra droguería"}
    ).execute().data[0]

    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
    )

    try:
        with pytest.raises(ValidationError):
            validar_extraccion(
                service_client,
                extraction_id=extraction["id"],
                usuario_id=seed_usuario_sistema["id"],
                proceso_comercial_id=otro_proceso["id"],
            )
    finally:
        service_client.table("procesos_comerciales").delete().eq("id", otro_proceso["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_validar_no_pisa_proceso_comercial_id_ya_vinculado(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    otro_proceso = service_client.table("procesos_comerciales").insert(
        {"drogueria_id": seed_drogueria["id"], "clase": "cotizacion", "nombre": "Otro proceso"}
    ).execute().data[0]

    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    try:
        with pytest.raises(ConflictError):
            validar_extraccion(
                service_client,
                extraction_id=extraction["id"],
                usuario_id=seed_usuario_sistema["id"],
                proceso_comercial_id=otro_proceso["id"],
            )
    finally:
        service_client.table("procesos_comerciales").delete().eq("id", otro_proceso["id"]).execute()


@pytest.mark.integration
def test_validar_orden_compra_no_implementado(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "orden_compra",
        filas=[{"numero_renglon": "1", "descripcion": "x", "cantidad": "1", "precio_unitario": "1"}],
        columnas=["numero_renglon", "descripcion", "cantidad", "precio_unitario"],
    )

    with pytest.raises(ValidationError):
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=seed_proceso_comercial["id"],
        )


@pytest.mark.integration
def test_validar_extraccion_inexistente_levanta_not_found(service_client, seed_usuario_sistema):
    with pytest.raises(NotFoundError):
        validar_extraccion(
            service_client,
            extraction_id="00000000-0000-0000-0000-000000000000",
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=None,
        )


@pytest.mark.integration
def test_validar_comparativa_calcula_posicion_precio_y_adjudicacion_estimada(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "comparativa",
        filas=[
            {"renglon": "1", "proveedor": "Proveedor A", "marca": "ELEA", "precio": "12.50", "cliente": "X"},
            {"renglon": "1", "proveedor": "Proveedor B", "marca": "sin marca", "precio": "10.00", "cliente": "X"},
            {"renglon": "1", "proveedor": "Proveedor C", "marca": "OTRA", "precio": "15.00", "cliente": "X"},
        ],
        columnas=["renglon", "proveedor", "marca", "precio", "cliente"],
    )

    resultado = validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    assert resultado.filas_creadas == 3
    assert resultado.comparativa_id is not None
    assert resultado.reemplazo_version_anterior is False

    ofertas = (
        service_client.table("ofertas_items")
        .select("*")
        .eq("comparativa_id", resultado.comparativa_id)
        .execute()
        .data
    )
    por_proveedor = {o["proveedor"]: o for o in ofertas}
    assert por_proveedor["Proveedor B"]["posicion_precio"] == 1
    assert por_proveedor["Proveedor B"]["adjudicacion_estimada"] is True
    assert por_proveedor["Proveedor A"]["posicion_precio"] == 2
    assert por_proveedor["Proveedor A"]["adjudicacion_estimada"] is False
    assert por_proveedor["Proveedor C"]["posicion_precio"] == 3
    assert por_proveedor["Proveedor C"]["es_drogueria_propia"] is False
    assert por_proveedor["Proveedor C"]["descripcion"] == "OTRA"

    comparativa = (
        service_client.table("comparativas")
        .select("*")
        .eq("id", resultado.comparativa_id)
        .execute()
        .data[0]
    )
    assert comparativa["cantidad_proveedores"] == 3
    assert comparativa["items_analizados"] == 1
    assert comparativa["es_vigente"] is True
    assert comparativa["version_numero"] == 1


@pytest.mark.integration
def test_validar_comparativa_linkea_item_proceso_id_por_numero_renglon(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    item_existente = service_client.table("items_proceso").insert(
        {
            "proceso_comercial_id": seed_proceso_comercial["id"],
            "drogueria_id": seed_drogueria["id"],
            "numero_renglon": 1,
            "descripcion": "Renglón ya materializado",
            "cantidad": "10",
        }
    ).execute().data[0]

    extraction = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "10.00", "cliente": "X"}],
        columnas=["renglon", "proveedor", "marca", "precio", "cliente"],
    )

    try:
        resultado = validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=seed_proceso_comercial["id"],
        )
        oferta = (
            service_client.table("ofertas_items")
            .select("item_proceso_id")
            .eq("comparativa_id", resultado.comparativa_id)
            .execute()
            .data[0]
        )
        assert oferta["item_proceso_id"] == item_existente["id"]
    finally:
        service_client.table("ofertas_items").update({"item_proceso_id": None}).eq(
            "item_proceso_id", item_existente["id"]
        ).execute()
        service_client.table("items_proceso").delete().eq("id", item_existente["id"]).execute()


@pytest.mark.integration
def test_validar_comparativa_segunda_vez_versiona_y_notifica(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    admin = service_client.auth.admin.create_user(
        {"email": f"admin-test-{seed_usuario_sistema['id']}@seed.local", "password": "x" * 20, "email_confirm": True}
    )
    admin_id = admin.user.id
    service_client.table("usuarios").insert(
        {"id": admin_id, "drogueria_id": seed_drogueria["id"], "rol": "admin", "nombre": "Admin de test"}
    ).execute()

    try:
        extraction_1 = seed_extraction_result_factory(
            "comparativa",
            filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "10.00", "cliente": "X"}],
            columnas=["renglon", "proveedor", "marca", "precio", "cliente"],
        )
        resultado_1 = validar_extraccion(
            service_client,
            extraction_id=extraction_1["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=seed_proceso_comercial["id"],
        )
        assert resultado_1.reemplazo_version_anterior is False

        extraction_2 = seed_extraction_result_factory(
            "comparativa",
            filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "9.00", "cliente": "X"}],
            columnas=["renglon", "proveedor", "marca", "precio", "cliente"],
        )
        resultado_2 = validar_extraccion(
            service_client,
            extraction_id=extraction_2["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=seed_proceso_comercial["id"],
        )

        assert resultado_2.reemplazo_version_anterior is True

        comparativa_vieja = (
            service_client.table("comparativas")
            .select("es_vigente")
            .eq("id", resultado_1.comparativa_id)
            .execute()
            .data[0]
        )
        assert comparativa_vieja["es_vigente"] is False

        comparativa_nueva = (
            service_client.table("comparativas")
            .select("*")
            .eq("id", resultado_2.comparativa_id)
            .execute()
            .data[0]
        )
        assert comparativa_nueva["es_vigente"] is True
        assert comparativa_nueva["version_numero"] == 2
        assert comparativa_nueva["reemplaza_id"] == resultado_1.comparativa_id

        notificaciones = (
            service_client.table("notificaciones")
            .select("*")
            .eq("comparativa_id", resultado_2.comparativa_id)
            .execute()
            .data
        )
        assert len(notificaciones) == 1
        assert notificaciones[0]["destinatario_id"] == admin_id
        assert notificaciones[0]["tipo"] == "comparativa_disponible"
    finally:
        service_client.table("notificaciones").delete().eq("destinatario_id", admin_id).execute()
        service_client.table("usuarios").delete().eq("id", admin_id).execute()
        service_client.auth.admin.delete_user(admin_id)
