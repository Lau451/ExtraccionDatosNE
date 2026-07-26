import csv as csv_module
import secrets
import uuid
from decimal import Decimal

import pytest

from services.presupuestacion.core.exceptions import (
    ConflictError,
    ExtraccionNoDisponibleError,
    NotFoundError,
    ValidationError,
)
from services.presupuestacion.extraccion.service import (
    _filas_a_materializar,
    _leer_filas_csv,
    _validar_filas_override,
    leer_filas_extraccion,
    validar_extraccion,
)


def test_leer_filas_csv_sin_path_levanta_extraccion_no_disponible():
    with pytest.raises(ExtraccionNoDisponibleError):
        _leer_filas_csv(None)


def test_leer_filas_csv_con_oserror_levanta_extraccion_no_disponible(tmp_path):
    # Abrir un directorio como si fuera un archivo dispara OSError (IsADirectoryError/
    # PermissionError según el SO) — es el mismo síntoma que un volumen no montado.
    directorio = tmp_path / "no-es-un-archivo"
    directorio.mkdir()

    with pytest.raises(ExtraccionNoDisponibleError):
        _leer_filas_csv(str(directorio))


def _escribir_csv(tmp_path, columnas: list[str], filas: list[dict[str, str]]):
    csv_path = tmp_path / "extraccion.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as archivo:
        writer = csv_module.DictWriter(archivo, fieldnames=columnas, delimiter=";")
        writer.writeheader()
        writer.writerows(filas)
    return str(csv_path)


def test_leer_filas_extraccion_licitacion_devuelve_columnas_y_filas_del_csv(tmp_path):
    csv_path = _escribir_csv(
        tmp_path,
        columnas=["item", "cantidad", "descripcion", "origen"],
        filas=[
            {"item": "1", "cantidad": "10", "descripcion": "Ibuprofeno 600mg", "origen": "pliego"},
            {"item": "2", "cantidad": "5", "descripcion": "Gasa estéril", "origen": "pliego"},
        ],
    )

    resultado = leer_filas_extraccion(
        {
            "id": "extraction-1",
            "document_type": "licitacion",
            "csv_disk_path": csv_path,
            "row_count": 2,
        }
    )

    assert resultado.extraction_id == "extraction-1"
    assert resultado.document_type == "licitacion"
    assert resultado.row_count == 2
    assert resultado.filas_leidas == 2
    assert resultado.editable is True
    assert resultado.columnas == ["item", "cantidad", "descripcion", "origen"]
    assert resultado.filas[0]["descripcion"] == "Ibuprofeno 600mg"


def test_leer_filas_extraccion_comparativa_devuelve_columnas_propias(tmp_path):
    csv_path = _escribir_csv(
        tmp_path,
        columnas=["renglon", "proveedor", "marca", "precio"],
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "ELEA", "precio": "12.50"}],
    )

    resultado = leer_filas_extraccion(
        {
            "id": "extraction-2",
            "document_type": "comparativa",
            "csv_disk_path": csv_path,
            "row_count": 1,
        }
    )

    assert resultado.document_type == "comparativa"
    assert resultado.columnas == ["renglon", "proveedor", "marca", "precio"]
    assert resultado.filas[0]["proveedor"] == "Proveedor A"


def test_leer_filas_extraccion_mas_de_500_filas_no_es_editable_y_no_manda_filas(tmp_path):
    filas = [
        {"item": str(i), "cantidad": "1", "descripcion": f"Item {i}"} for i in range(1, 502)
    ]
    csv_path = _escribir_csv(tmp_path, columnas=["item", "cantidad", "descripcion"], filas=filas)

    resultado = leer_filas_extraccion(
        {
            "id": "extraction-3",
            "document_type": "licitacion",
            "csv_disk_path": csv_path,
            "row_count": 501,
        }
    )

    assert resultado.filas_leidas == 501
    assert resultado.editable is False
    assert resultado.filas == []
    # columnas se sigue informando aunque no se manden las filas -- es diagnóstico,
    # no el material a editar.
    assert resultado.columnas == ["item", "cantidad", "descripcion"]


def test_leer_filas_extraccion_orden_compra_no_tiene_lectura_implementada():
    with pytest.raises(ValidationError):
        leer_filas_extraccion(
            {
                "id": "extraction-4",
                "document_type": "orden_compra",
                "csv_disk_path": None,
                "row_count": 0,
            }
        )


def test_leer_filas_extraccion_csv_no_disponible_levanta_extraccion_no_disponible():
    with pytest.raises(ExtraccionNoDisponibleError):
        leer_filas_extraccion(
            {
                "id": "extraction-5",
                "document_type": "licitacion",
                "csv_disk_path": None,
                "row_count": 0,
            }
        )


# --- _validar_filas_override (Phase 4, §3 del design) -----------------------------


def test_validar_filas_override_none_no_hace_nada():
    assert _validar_filas_override(None, document_type="licitacion") is None


def test_validar_filas_override_lista_vacia_levanta_validation_error():
    with pytest.raises(ValidationError):
        _validar_filas_override([], document_type="licitacion")


def test_validar_filas_override_mas_de_500_levanta_validation_error():
    filas = [
        {"item": str(i), "descripcion": f"Item {i}", "cantidad": "1"} for i in range(1, 502)
    ]
    with pytest.raises(ValidationError):
        _validar_filas_override(filas, document_type="licitacion")


def test_validar_filas_override_tipo_cruzado_levanta_validation_error():
    # Filas con forma de comparativa ("renglon") enviadas para una extracción de
    # licitación -- pydantic ya no puede distinguirlo acá (llegan como dict plano),
    # así que la validación de forma es responsabilidad de esta función.
    filas_de_comparativa = [
        {"renglon": "1", "proveedor": "Proveedor A", "marca": "ELEA", "precio": "10.00"}
    ]
    with pytest.raises(ValidationError):
        _validar_filas_override(filas_de_comparativa, document_type="licitacion")


def test_validar_filas_override_valor_no_numerico_levanta_validation_error():
    filas = [{"item": "1", "descripcion": "Item de test", "cantidad": "12 unidades"}]
    with pytest.raises(ValidationError):
        _validar_filas_override(filas, document_type="licitacion")


def test_validar_filas_override_acumula_errores_de_multiples_filas():
    # La fila 1 tiene descripcion vacía, la fila 2 tiene un item no numérico -- ambos
    # errores deben aparecer en el mismo 422 (§3: "se recorren las 80, se acumulan
    # todos los errores").
    filas = [
        {"item": "1", "descripcion": "", "cantidad": "1"},
        {"item": "no-es-un-numero", "descripcion": "Item de test", "cantidad": "1"},
    ]
    with pytest.raises(ValidationError) as excinfo:
        _validar_filas_override(filas, document_type="licitacion")

    mensaje = str(excinfo.value)
    assert "fila 1" in mensaje
    assert "fila 2" in mensaje


# --- _filas_a_materializar (Phase 4, §2.2 del design) ------------------------------


def test_filas_a_materializar_sin_override_lee_del_csv(tmp_path):
    csv_path = _escribir_csv(
        tmp_path,
        columnas=["item", "cantidad", "descripcion"],
        filas=[{"item": "1", "cantidad": "10", "descripcion": "Item de test"}],
    )

    resultado = _filas_a_materializar({"csv_disk_path": csv_path}, None)

    assert resultado == [{"item": "1", "cantidad": "10", "descripcion": "Item de test"}]


def test_filas_a_materializar_con_override_no_lee_el_csv():
    # csv_disk_path apunta a un path inexistente a propósito: si `_filas_a_materializar`
    # intentara leerlo, esto reventaría con `ExtraccionNoDisponibleError`. Que no
    # reviente es la prueba de que el override tiene prioridad y el CSV nunca se toca (D2).
    override = [{"item": "1", "cantidad": "10", "descripcion": "Editado"}]

    resultado = _filas_a_materializar({"csv_disk_path": "/no/existe/este/path.csv"}, override)

    assert resultado == override


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


@pytest.mark.integration
def test_validar_comparativa_reemplazo_notifica_via_service_y_respeta_filtros(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    crear_usuario_autenticado,
):
    # D6 (5.4) -- cubre los tres defectos de una sola pasada: #1 (notificacion_entregas
    # se crea porque ahora se llama a notificaciones/service.py, no al insert directo del
    # repo local), #3 (excluye al actor, filtra por activo y por rol/droguería).
    #
    # actor_admin_id se crea a mano (no vía crear_usuario_autenticado): al ser quien
    # ejecuta validar_extraccion, su id queda referenciado por
    # extraction_results.validado_por e historial_cambios.usuario_id -- filas que borra
    # `seed_extraction_result_factory` en SU propio teardown, que corre DESPUÉS del de
    # `crear_usuario_autenticado` (pytest destruye fixtures en el orden inverso al de la
    # firma del test). Si el auth user se borrara automáticamente ahí, todavía sería
    # referenciado y el delete_user fallaría en cascada. Se limpia todo a mano, en el
    # orden correcto, en el finally de este test.
    actor_admin_auth = service_client.auth.admin.create_user(
        {
            "email": f"actor-admin-{uuid.uuid4()}@seed.local",
            "password": secrets.token_urlsafe(24),
            "email_confirm": True,
        }
    )
    actor_admin_id = actor_admin_auth.user.id
    service_client.table("usuarios").insert(
        {
            "id": actor_admin_id,
            "drogueria_id": seed_drogueria["id"],
            "rol": "admin",
            "nombre": "Admin actor (test)",
        }
    ).execute()

    destinatario_gerencia_id, _ = crear_usuario_autenticado(
        rol="gerencia", drogueria_id=seed_drogueria["id"]
    )
    destinatario_lider_id, _ = crear_usuario_autenticado(
        rol="lider_comercial", drogueria_id=seed_drogueria["id"]
    )
    otro_rol_id, _ = crear_usuario_autenticado(rol="comercial", drogueria_id=seed_drogueria["id"])

    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería (D6 test)",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": f"otra-d6-{uuid.uuid4()}@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]
    # Creado manual (no vía crear_usuario_autenticado): esa fixture borra el usuario en
    # SU propio teardown, que corre DESPUÉS del `finally` de este test -- borrar acá la
    # droguería antes de eso revienta fk_usuarios_drogueria. Se crea y se borra a mano,
    # en el orden correcto, dentro del try/finally de este test.
    otra_drogueria_auth = service_client.auth.admin.create_user(
        {
            "email": f"otra-d6-admin-{uuid.uuid4()}@seed.local",
            "password": secrets.token_urlsafe(24),
            "email_confirm": True,
        }
    )
    otra_drogueria_admin_id = otra_drogueria_auth.user.id
    service_client.table("usuarios").insert(
        {
            "id": otra_drogueria_admin_id,
            "drogueria_id": otra_drogueria["id"],
            "rol": "admin",
            "nombre": "Admin otra droguería (test)",
        }
    ).execute()

    inactivo_auth = service_client.auth.admin.create_user(
        {
            "email": f"inactivo-{uuid.uuid4()}@seed.local",
            "password": secrets.token_urlsafe(24),
            "email_confirm": True,
        }
    )
    inactivo_admin_id = inactivo_auth.user.id
    service_client.table("usuarios").insert(
        {
            "id": inactivo_admin_id,
            "drogueria_id": seed_drogueria["id"],
            "rol": "admin",
            "nombre": "Admin inactivo (test)",
            "activo": False,
        }
    ).execute()

    resultado_1 = None
    resultado_2 = None
    try:
        extraction_1 = seed_extraction_result_factory(
            "comparativa",
            filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "10.00"}],
            columnas=["renglon", "proveedor", "marca", "precio"],
        )
        resultado_1 = validar_extraccion(
            service_client,
            extraction_id=extraction_1["id"],
            usuario_id=actor_admin_id,
            proceso_comercial_id=seed_proceso_comercial["id"],
        )

        extraction_2 = seed_extraction_result_factory(
            "comparativa",
            filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "9.00"}],
            columnas=["renglon", "proveedor", "marca", "precio"],
        )
        resultado_2 = validar_extraccion(
            service_client,
            extraction_id=extraction_2["id"],
            usuario_id=actor_admin_id,
            proceso_comercial_id=seed_proceso_comercial["id"],
        )
        assert resultado_2.reemplazo_version_anterior is True

        notificaciones = (
            service_client.table("notificaciones")
            .select("*")
            .eq("comparativa_id", resultado_2.comparativa_id)
            .execute()
            .data
        )
        destinatarios = {n["destinatario_id"] for n in notificaciones}

        # exactamente admin/gerencia/lider_comercial activos de la misma droguería,
        # sin el actor -- ni inactivos, ni otro rol, ni otra droguería.
        assert destinatarios == {destinatario_gerencia_id, destinatario_lider_id}
        assert actor_admin_id not in destinatarios
        assert inactivo_admin_id not in destinatarios
        assert otro_rol_id not in destinatarios
        assert otra_drogueria_admin_id not in destinatarios

        for notificacion in notificaciones:
            assert notificacion["tipo"] == "comparativa_disponible"
            assert notificacion["metadata"]["extraction_result_id"] == extraction_2["id"]
            entregas = (
                service_client.table("notificacion_entregas")
                .select("*")
                .eq("notificacion_id", notificacion["id"])
                .execute()
                .data
            )
            # defecto #1 (fix): antes el insert directo del repo local saltaba
            # notificacion_entregas por completo -- ahora sí hay al menos una fila.
            assert len(entregas) >= 1
    finally:
        # notificaciones.destinatario_id (fk_no_dest) NO tiene ON DELETE CASCADE: hay que
        # borrar las notificaciones ANTES de que el teardown de `crear_usuario_autenticado`
        # borre los usuarios destinatarios, o ese delete_user revienta en cascada -- no
        # alcanza con el orden de aparición en la firma del test, pytest destruye
        # fixtures en el orden inverso al de esa firma, no en el orden en que las cosas
        # se referencian entre sí.
        if resultado_2 is not None:
            service_client.table("notificaciones").delete().eq(
                "comparativa_id", resultado_2.comparativa_id
            ).execute()

        # Rompe las referencias a actor_admin_id ANTES de borrar su auth user (ver
        # comentario largo más arriba, junto a la creación de actor_admin_auth).
        for resultado in (resultado_1, resultado_2):
            if resultado is not None and resultado.comparativa_id is not None:
                service_client.table("historial_cambios").delete().eq(
                    "comparativa_id", resultado.comparativa_id
                ).execute()
        service_client.table("extraction_results").update({"validado_por": None}).eq(
            "drogueria_id", seed_drogueria["id"]
        ).eq("validado_por", actor_admin_id).execute()
        service_client.table("usuarios").delete().eq("id", actor_admin_id).execute()
        service_client.auth.admin.delete_user(actor_admin_id)

        service_client.table("usuarios").delete().eq("id", inactivo_admin_id).execute()
        service_client.auth.admin.delete_user(inactivo_admin_id)
        service_client.table("usuarios").delete().eq("id", otra_drogueria_admin_id).execute()
        service_client.auth.admin.delete_user(otra_drogueria_admin_id)
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_validar_comparativa_reemplazo_sin_destinatarios_elegibles_no_notifica_ni_falla(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    # D6 (5.6) -- seed_drogueria no tiene ningún usuario admin/gerencia/lider_comercial;
    # seed_usuario_sistema es rol="sistema" (fuera del filtro). Cero destinatarios
    # elegibles NO es un error: la validación debe completarse igual.
    extraction_1 = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "10.00"}],
        columnas=["renglon", "proveedor", "marca", "precio"],
    )
    validar_extraccion(
        service_client,
        extraction_id=extraction_1["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    extraction_2 = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "9.00"}],
        columnas=["renglon", "proveedor", "marca", "precio"],
    )
    resultado_2 = validar_extraccion(
        service_client,
        extraction_id=extraction_2["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    assert resultado_2.reemplazo_version_anterior is True

    extraction_final = (
        service_client.table("extraction_results")
        .select("validado")
        .eq("id", extraction_2["id"])
        .execute()
        .data[0]
    )
    assert extraction_final["validado"] is True

    notificaciones = (
        service_client.table("notificaciones")
        .select("*")
        .eq("comparativa_id", resultado_2.comparativa_id)
        .execute()
        .data
    )
    assert notificaciones == []


@pytest.mark.integration
def test_validar_comparativa_registra_historial_de_creacion(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "10.00", "cliente": "X"}],
        columnas=["renglon", "proveedor", "marca", "precio", "cliente"],
    )

    resultado = validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    historial = (
        service_client.table("historial_cambios")
        .select("*")
        .eq("comparativa_id", resultado.comparativa_id)
        .execute()
        .data
    )
    assert len(historial) == 1
    assert historial[0]["tipo_cambio"] == "creacion"
    assert historial[0]["usuario_id"] == seed_usuario_sistema["id"]


@pytest.mark.integration
def test_validar_comparativa_reemplazo_registra_historial_de_invalidacion(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
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

    extraction_2 = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "9.00", "cliente": "X"}],
        columnas=["renglon", "proveedor", "marca", "precio", "cliente"],
    )
    validar_extraccion(
        service_client,
        extraction_id=extraction_2["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
    )

    historial_vieja = (
        service_client.table("historial_cambios")
        .select("*")
        .eq("comparativa_id", resultado_1.comparativa_id)
        .eq("campo", "es_vigente")
        .execute()
        .data
    )
    assert len(historial_vieja) == 1
    assert historial_vieja[0]["valor_anterior"] == "true"
    assert historial_vieja[0]["valor_nuevo"] == "false"


# --- Phase 4: materialización con override (`filas` del body, D2/D3/D7) -----------


@pytest.mark.integration
def test_validar_licitacion_con_filas_editadas_materializa_desde_el_body(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[
            {"item": "1", "cantidad": "10", "descripcion": "Ibuprofeno 600mg x30", "origen": "pliego"},
        ],
        columnas=["item", "cantidad", "descripcion", "origen"],
    )
    with open(extraction["csv_disk_path"], encoding="utf-8") as archivo:
        csv_original = archivo.read()

    filas_editadas = [
        {"item": "1", "descripcion": "Ibuprofeno 600mg x30 (editado)", "cantidad": "25"},
    ]

    resultado = validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
        filas_override=filas_editadas,
    )

    assert resultado.filas_creadas == 1

    items = (
        service_client.table("items_proceso")
        .select("*")
        .eq("proceso_comercial_id", seed_proceso_comercial["id"])
        .execute()
        .data
    )
    assert len(items) == 1
    assert items[0]["descripcion"] == "Ibuprofeno 600mg x30 (editado)"
    assert Decimal(str(items[0]["cantidad"])) == Decimal("25")

    # el CSV crudo permanece intacto (D2): el override nunca lo reescribe
    with open(extraction["csv_disk_path"], encoding="utf-8") as archivo:
        assert archivo.read() == csv_original

    extraction_final = (
        service_client.table("extraction_results")
        .select("row_count")
        .eq("id", extraction["id"])
        .execute()
        .data[0]
    )
    # row_count sigue describiendo lo que dijo la IA, no lo que confirmó el humano
    assert extraction_final["row_count"] == 1


@pytest.mark.integration
def test_validar_comparativa_con_fila_agregada_incluye_renglon_nuevo_y_recalcula_posiciones(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "comparativa",
        filas=[
            {"renglon": "1", "proveedor": "Proveedor A", "marca": "ELEA", "precio": "12.50", "cliente": "X"},
        ],
        columnas=["renglon", "proveedor", "marca", "precio", "cliente"],
    )

    # El humano agrega un proveedor más barato que Gemini se salteó -- fila nueva,
    # sin equivalente en el CSV original.
    filas_con_agregada = [
        {"renglon": "1", "proveedor": "Proveedor A", "marca": "ELEA", "precio": "12.50"},
        {"renglon": "1", "proveedor": "Proveedor B", "marca": "sin marca", "precio": "9.00"},
    ]

    resultado = validar_extraccion(
        service_client,
        extraction_id=extraction["id"],
        usuario_id=seed_usuario_sistema["id"],
        proceso_comercial_id=seed_proceso_comercial["id"],
        filas_override=filas_con_agregada,
    )

    assert resultado.filas_creadas == 2

    ofertas = (
        service_client.table("ofertas_items")
        .select("*")
        .eq("comparativa_id", resultado.comparativa_id)
        .execute()
        .data
    )
    por_proveedor = {o["proveedor"]: o for o in ofertas}
    assert set(por_proveedor) == {"Proveedor A", "Proveedor B"}
    # posiciones recalculadas con la fila agregada incluida: el más barato es ahora
    # el que no estaba en el CSV original
    assert por_proveedor["Proveedor B"]["posicion_precio"] == 1
    assert por_proveedor["Proveedor B"]["adjudicacion_estimada"] is True
    assert por_proveedor["Proveedor A"]["posicion_precio"] == 2
    assert por_proveedor["Proveedor A"]["adjudicacion_estimada"] is False


@pytest.mark.integration
def test_validar_fila_47_de_80_invalida_no_escribe_nada(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    # 80 filas válidas salvo la 47 (cantidad no numérica) -- corazón de §3: se recorren
    # las 80, se acumula el error, y NO hay ningún write porque la validación corre
    # antes de _resolver_proceso_comercial_id (el primer write de la operación).
    filas_80 = [
        {"item": str(i), "descripcion": f"Item {i}", "cantidad": "1"} for i in range(1, 81)
    ]
    filas_80[46] = {"item": "47", "descripcion": "Item 47", "cantidad": "12 unidades"}

    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "CSV original", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
    )

    with pytest.raises(ValidationError) as excinfo:
        validar_extraccion(
            service_client,
            extraction_id=extraction["id"],
            usuario_id=seed_usuario_sistema["id"],
            proceso_comercial_id=seed_proceso_comercial["id"],
            filas_override=filas_80,
        )
    assert "fila 47" in str(excinfo.value)

    extraction_final = (
        service_client.table("extraction_results")
        .select("validado, validado_por, validado_at, proceso_comercial_id")
        .eq("id", extraction["id"])
        .execute()
        .data[0]
    )
    # cero writes: ni el flip de validado ni el primer write (proceso_comercial_id)
    # corrieron -- la validación pasó ANTES de _resolver_proceso_comercial_id
    assert extraction_final["validado"] is False
    assert extraction_final["validado_por"] is None
    assert extraction_final["validado_at"] is None
    assert extraction_final["proceso_comercial_id"] is None

    items = (
        service_client.table("items_proceso")
        .select("id")
        .eq("proceso_comercial_id", seed_proceso_comercial["id"])
        .execute()
        .data
    )
    assert items == []
