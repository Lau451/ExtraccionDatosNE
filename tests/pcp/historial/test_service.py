"""3.2 / 3.3 (openspec/changes/gestor-pcp/tasks.md Fase 3) -- pcp-historial es
append-only: `agregar_evento` es el único escritor y no existe ningún método
en `services.pcp.historial.service` que edite o borre una fila existente.

RED hasta que 3.4 cree `services/pcp/historial/{models,repository,service}.py`.
"""

import inspect

import pytest

from services.pcp.historial.service import agregar_evento, listar_eventos


# ---------------------------------------------------------------------------
# 3.2 -- un evento de PCP se escribe en pcp_historial, nunca en historial_cambios
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_agregar_evento_escribe_en_pcp_historial_no_en_historial_cambios(
    service_client, seed_drogueria, seed_pcp_factory
):
    pcp = seed_pcp_factory()

    evento = agregar_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        tipo_evento="creada",
        payload={"origen": "manual"},
    )

    assert evento["pcp_id"] == pcp["id"]
    assert evento["tipo_evento"] == "creada"
    assert evento["payload"] == {"origen": "manual"}

    en_pcp_historial = (
        service_client.table("pcp_historial").select("id").eq("id", evento["id"]).execute().data
    )
    assert len(en_pcp_historial) == 1

    # historial_cambios no tiene columna pcp_id (D6: PCP no extiende
    # EntidadAuditable); la prueba directa de "nunca escribe ahí" es que la
    # única fila que le corresponde al presupuesto de este PCP sigue vacía --
    # nada más que `agregar_evento` tocó esta tabla en este test.
    en_historial_cambios = (
        service_client.table("historial_cambios")
        .select("id")
        .eq("presupuesto_id", pcp["presupuesto_id"])
        .execute()
        .data
    )
    assert en_historial_cambios == []


@pytest.mark.integration
def test_agregar_evento_persiste_usuario_y_origen_para_un_tipo_distinto(
    service_client, seed_drogueria, seed_pcp_factory, seed_usuario_sistema
):
    """Triangulación: tipo_evento y payload distintos al primer caso, más
    usuario_id/origen -- si `agregar_evento` estuviera hardcodeado al primer
    caso (Fake It), esta aserción lo expone."""
    pcp = seed_pcp_factory()

    evento = agregar_evento(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        tipo_evento="estado_cambiado",
        payload={"estado_anterior": "nueva", "estado_nuevo": "en_gestion"},
        usuario_id=seed_usuario_sistema["id"],
        origen="manual",
    )

    assert evento["tipo_evento"] == "estado_cambiado"
    assert evento["payload"] == {"estado_anterior": "nueva", "estado_nuevo": "en_gestion"}
    assert evento["usuario_id"] == seed_usuario_sistema["id"]
    assert evento["origen"] == "manual"


@pytest.mark.integration
def test_listar_eventos_devuelve_los_eventos_del_pcp_indicado(
    service_client, seed_drogueria, seed_pcp_factory
):
    pcp_a = seed_pcp_factory()
    pcp_b = seed_pcp_factory()
    agregar_evento(
        service_client, drogueria_id=seed_drogueria["id"], pcp_id=pcp_a["id"], tipo_evento="creada"
    )
    agregar_evento(
        service_client, drogueria_id=seed_drogueria["id"], pcp_id=pcp_b["id"], tipo_evento="creada"
    )

    eventos_a = listar_eventos(service_client, pcp_id=pcp_a["id"], drogueria_id=seed_drogueria["id"])

    assert {e["pcp_id"] for e in eventos_a} == {pcp_a["id"]}


# ---------------------------------------------------------------------------
# 3.3 -- ningún método del módulo edita o borra una fila existente
# ---------------------------------------------------------------------------


def test_historial_service_no_expone_metodos_de_mutacion_o_borrado():
    """Prueba estructural: la forma del módulo, no el comportamiento de la
    BD, es la primera línea de defensa. `pcp_historial` no tiene políticas
    RLS de UPDATE/DELETE (0012_pcp_extras.sql M7), así que ni siquiera debe
    existir la función que intentaría usarlas."""
    from services.pcp.historial import service as historial_service

    funciones_publicas = {
        nombre
        for nombre, miembro in inspect.getmembers(historial_service, inspect.isfunction)
        if not nombre.startswith("_") and miembro.__module__ == historial_service.__name__
    }

    nombres_de_mutacion_o_borrado = {
        nombre
        for nombre in funciones_publicas
        if any(
            fragmento in nombre
            for fragmento in ("actualizar", "eliminar", "modificar", "borrar", "editar")
        )
    }

    assert not nombres_de_mutacion_o_borrado, (
        f"services/pcp/historial/service.py expone métodos de mutación/borrado: "
        f"{nombres_de_mutacion_o_borrado} (viola D6/append-only)"
    )
    assert funciones_publicas == {"agregar_evento", "listar_eventos"}


@pytest.mark.integration
def test_actualizar_pcp_historial_via_db_es_rechazado(
    service_client, seed_drogueria, seed_pcp_factory, crear_usuario_autenticado
):
    """Defensa en profundidad (spec pcp-historial: 'Reject editing a history
    entry') -- aunque el servicio no expone ningún método de edición, RLS
    también lo rechaza. `pcp_historial` no tiene política UPDATE
    (0012_pcp_extras.sql M7: 'RLS habilitado sin política = deny by
    default'), así que el UPDATE de un usuario autenticado no ve ninguna fila
    para actualizar -- Postgres/PostgREST no fallan con un error (el
    privilegio GRANT de tabla lo tiene, es la ausencia de política RLS la que
    actúa), devuelven éxito con 0 filas afectadas. Confirmado empíricamente
    contra el proyecto de test antes de escribir esta aserción: un intento
    real de UPDATE devuelve `data == []` y dejó la fila sin tocar."""
    pcp = seed_pcp_factory()
    evento = agregar_evento(
        service_client, drogueria_id=seed_drogueria["id"], pcp_id=pcp["id"], tipo_evento="creada"
    )
    _, cliente_compras = crear_usuario_autenticado(rol="compras", drogueria_id=seed_drogueria["id"])

    respuesta = (
        cliente_compras.table("pcp_historial")
        .update({"tipo_evento": "importada"})
        .eq("id", evento["id"])
        .execute()
    )
    assert respuesta.data == []

    intacto = (
        service_client.table("pcp_historial")
        .select("tipo_evento")
        .eq("id", evento["id"])
        .execute()
        .data[0]
    )
    assert intacto["tipo_evento"] == "creada"


@pytest.mark.integration
def test_eliminar_pcp_historial_via_db_es_rechazado(
    service_client, seed_drogueria, seed_pcp_factory, crear_usuario_autenticado
):
    """Defensa en profundidad (spec pcp-historial: 'Reject deleting a history
    entry') -- mismo mecanismo que el UPDATE: sin política DELETE, RLS
    esconde toda fila del DELETE de un usuario autenticado (0 filas
    afectadas, sin error), confirmado empíricamente igual que arriba."""
    pcp = seed_pcp_factory()
    evento = agregar_evento(
        service_client, drogueria_id=seed_drogueria["id"], pcp_id=pcp["id"], tipo_evento="creada"
    )
    _, cliente_compras = crear_usuario_autenticado(rol="compras", drogueria_id=seed_drogueria["id"])

    respuesta = cliente_compras.table("pcp_historial").delete().eq("id", evento["id"]).execute()
    assert respuesta.data == []

    aun_existe = (
        service_client.table("pcp_historial").select("id").eq("id", evento["id"]).execute().data
    )
    assert len(aun_existe) == 1
