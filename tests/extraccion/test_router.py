import secrets

import pytest

from services.presupuestacion.core.auth import UsuarioPerfil
from services.presupuestacion.core.exceptions import ExtraccionNoDisponibleError, ForbiddenError
from services.presupuestacion.extraccion import router
from services.presupuestacion.extraccion.models import ValidarExtraccionRequest


def _usuario(*, id: str, drogueria_id: str | None, rol: str = "comercial") -> UsuarioPerfil:
    return UsuarioPerfil(id=id, drogueria_id=drogueria_id, rol=rol)


@pytest.mark.integration
def test_listar_extracciones_validado_false_devuelve_solo_pendientes_de_la_propia_drogueria(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema, crear_usuario_autenticado,
):
    # RLS de verdad (er_sel / mismo_tenant): un usuario autenticado de la droguería A
    # solo puede ver sus propias extracciones, aunque exista una pendiente en la
    # droguería B (§8.1 -- no hay filtro manual por drogueria_id, la frontera es RLS).
    usuario_id, cliente_a = crear_usuario_autenticado(
        rol="comercial", drogueria_id=seed_drogueria["id"]
    )

    pendiente_propia = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
    )
    validada_propia = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
        validado=True,
    )

    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería (router test)",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": "otra-router@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]

    try:
        pendiente_ajena = service_client.table("extraction_results").insert(
            {
                "drogueria_id": otra_drogueria["id"],
                "document_type": "licitacion",
                "source_filename": "ajena.pdf",
                "source_sha256": secrets.token_hex(32),
                "row_count": 1,
                "csv_disk_path": None,
                "status": "completed",
                "validado": False,
            }
        ).execute().data[0]

        try:
            resultado = router.listar_extracciones_endpoint(
                validado=False,
                limit=50,
                offset=0,
                usuario=_usuario(id=usuario_id, drogueria_id=seed_drogueria["id"]),
                user_client=cliente_a,
            )
            ids = {r.id for r in resultado}

            assert pendiente_propia["id"] in ids
            assert validada_propia["id"] not in ids
            assert pendiente_ajena["id"] not in ids
        finally:
            service_client.table("extraction_results").delete().eq(
                "id", pendiente_ajena["id"]
            ).execute()
    finally:
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_obtener_filas_extraccion_licitacion_tipa_por_document_type(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "10", "descripcion": "Ibuprofeno 600mg", "origen": "pliego"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
    )

    resultado = router.obtener_filas_extraccion_endpoint(
        extraction["id"],
        usuario=_usuario(id=seed_usuario_sistema["id"], drogueria_id=seed_drogueria["id"]),
        user_client=service_client,
    )

    assert resultado.document_type == "licitacion"
    assert resultado.editable is True
    assert resultado.columnas == ["item", "cantidad", "descripcion", "origen"]
    assert resultado.filas[0]["descripcion"] == "Ibuprofeno 600mg"


@pytest.mark.integration
def test_obtener_filas_extraccion_comparativa_tipa_por_document_type(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "ELEA", "precio": "12.50"}],
        columnas=["renglon", "proveedor", "marca", "precio"],
    )

    resultado = router.obtener_filas_extraccion_endpoint(
        extraction["id"],
        usuario=_usuario(id=seed_usuario_sistema["id"], drogueria_id=seed_drogueria["id"]),
        user_client=service_client,
    )

    assert resultado.document_type == "comparativa"
    assert resultado.columnas == ["renglon", "proveedor", "marca", "precio"]
    assert resultado.filas[0]["proveedor"] == "Proveedor A"


@pytest.mark.integration
def test_obtener_filas_extraccion_de_otra_drogueria_da_forbidden_antes_de_tocar_el_disco(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    # csv_disk_path apunta a un archivo inexistente a propósito: si el chequeo de
    # pertenencia no precediera a la lectura, esto reventaría con
    # ExtraccionNoDisponibleError (o peor, un 500) en vez de ForbiddenError -- la
    # prueba de que el disco nunca se toca es justamente CUÁL excepción se levanta.
    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
        csv_disk_path="/no/existe/este/path.csv",
    )

    with pytest.raises(ForbiddenError):
        router.obtener_filas_extraccion_endpoint(
            extraction["id"],
            usuario=_usuario(id=seed_usuario_sistema["id"], drogueria_id="00000000-0000-0000-0000-000000000000"),
            user_client=service_client,
        )


@pytest.mark.integration
def test_obtener_filas_extraccion_csv_disk_path_null_da_503_de_dominio(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
        csv_disk_path=None,
    )

    with pytest.raises(ExtraccionNoDisponibleError):
        router.obtener_filas_extraccion_endpoint(
            extraction["id"],
            usuario=_usuario(id=seed_usuario_sistema["id"], drogueria_id=seed_drogueria["id"]),
            user_client=service_client,
        )


@pytest.mark.integration
def test_obtener_filas_extraccion_csv_disk_path_inaccesible_da_503_de_dominio(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema, tmp_path,
):
    directorio = tmp_path / "no-es-un-archivo"
    directorio.mkdir()

    extraction = seed_extraction_result_factory(
        "licitacion",
        filas=[{"item": "1", "cantidad": "1", "descripcion": "Item de test", "origen": "x"}],
        columnas=["item", "cantidad", "descripcion", "origen"],
        csv_disk_path=str(directorio),
    )

    with pytest.raises(ExtraccionNoDisponibleError):
        router.obtener_filas_extraccion_endpoint(
            extraction["id"],
            usuario=_usuario(id=seed_usuario_sistema["id"], drogueria_id=seed_drogueria["id"]),
            user_client=service_client,
        )


@pytest.mark.integration
def test_validar_extraccion_notificacion_de_reemplazo_falla_no_bloquea_la_validacion(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema, crear_usuario_autenticado, monkeypatch,
):
    # D6 (5.5) -- defecto #2 corregido: un fallo en crear_notificacion (ahora envuelto en
    # try/except, DESPUÉS del flip de validado) NO debe dejar la extracción en el peor
    # estado parcial posible (comparativa + ofertas creadas con validado=FALSE). El
    # endpoint sigue respondiendo con éxito (no levanta excepción -> 200 real vía FastAPI,
    # register_exception_handlers solo entra en juego cuando SÍ se levanta una excepción
    # de dominio) y `validado` queda en TRUE en la base.
    crear_usuario_autenticado(rol="admin", drogueria_id=seed_drogueria["id"])

    extraction_1 = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "10.00"}],
        columnas=["renglon", "proveedor", "marca", "precio"],
    )
    router.validar_extraccion_endpoint(
        extraction_1["id"],
        ValidarExtraccionRequest(proceso_comercial_id=seed_proceso_comercial["id"]),
        usuario=_usuario(id=seed_usuario_sistema["id"], drogueria_id=seed_drogueria["id"]),
        user_client=service_client,
    )

    extraction_2 = seed_extraction_result_factory(
        "comparativa",
        filas=[{"renglon": "1", "proveedor": "Proveedor A", "marca": "", "precio": "9.00"}],
        columnas=["renglon", "proveedor", "marca", "precio"],
    )

    monkeypatch.setattr(
        "services.presupuestacion.extraccion.service.crear_notificacion",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("smtp caído (test)")),
    )

    resultado = router.validar_extraccion_endpoint(
        extraction_2["id"],
        ValidarExtraccionRequest(proceso_comercial_id=seed_proceso_comercial["id"]),
        usuario=_usuario(id=seed_usuario_sistema["id"], drogueria_id=seed_drogueria["id"]),
        user_client=service_client,
    )

    assert resultado.reemplazo_version_anterior is True

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
        .eq("comparativa_id", resultado.comparativa_id)
        .execute()
        .data
    )
    assert notificaciones == []  # crear_notificacion nunca llegó a insertar nada
