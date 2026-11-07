import uuid

import pytest

from services.shared.exceptions import NotFoundError, ValidationError
from services.terceros.identidad.models import (
    ClienteRolUpdate,
    ProveedorRolUpdate,
    TerceroUpdate,
)
from services.terceros.identidad.service import (
    actualizar_rol_cliente,
    actualizar_rol_proveedor,
    actualizar_tercero,
    listar_clientes_con_tercero,
    listar_proveedores_con_tercero,
    listar_terceros,
    listar_terceros_paginado,
    obtener_cliente_con_tercero,
    obtener_proveedor_con_tercero,
    obtener_rol_cliente,
    obtener_rol_proveedor,
    obtener_tercero,
)


@pytest.mark.integration
def test_listar_terceros_incluye_flags_de_rol_sin_consulta_extra(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_cliente_factory, seed_rol_proveedor_factory
):
    solo_cliente = seed_tercero_factory(razon_social="Solo Cliente SA")
    solo_proveedor = seed_tercero_factory(razon_social="Solo Proveedor SA")
    ambos = seed_tercero_factory(razon_social="Ambos Roles SA")
    sin_rol = seed_tercero_factory(razon_social="Sin Rol SA")

    seed_rol_cliente_factory(solo_cliente["id"])
    seed_rol_proveedor_factory(solo_proveedor["id"])
    seed_rol_cliente_factory(ambos["id"])
    seed_rol_proveedor_factory(ambos["id"])

    listado = {
        fila["id"]: fila
        for fila in listar_terceros(service_client, drogueria_id=seed_drogueria["id"], activo=None)
    }

    assert listado[solo_cliente["id"]]["tiene_rol_cliente"] is True
    assert listado[solo_cliente["id"]]["tiene_rol_proveedor"] is False
    assert listado[solo_proveedor["id"]]["tiene_rol_cliente"] is False
    assert listado[solo_proveedor["id"]]["tiene_rol_proveedor"] is True
    assert listado[ambos["id"]]["tiene_rol_cliente"] is True
    assert listado[ambos["id"]]["tiene_rol_proveedor"] is True
    assert listado[sin_rol["id"]]["tiene_rol_cliente"] is False
    assert listado[sin_rol["id"]]["tiene_rol_proveedor"] is False


# ---------------------------------------------------------------------------
# Paginación server-side y búsqueda por texto (motivo: GestionTerceros.tsx
# renderizaba las 5541 filas de Nueva Era de una sola vez -- ver bug de
# truncado en 1000 filas más arriba en este mismo módulo).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listar_terceros_paginado_filtra_por_q_contra_postgres_real(
    service_client, seed_drogueria, seed_tercero_factory
):
    seed_tercero_factory(razon_social="Hospital Provincial Rosario", codigo_interno="C996")
    seed_tercero_factory(razon_social="Farmacia del Centro", codigo_interno="C100")

    items, total = listar_terceros_paginado(
        service_client, drogueria_id=seed_drogueria["id"], q="c996"
    )

    assert total == 1
    assert items[0]["razon_social"] == "Hospital Provincial Rosario"


@pytest.mark.integration
def test_listar_terceros_paginado_pagina_contra_postgres_real(
    service_client, seed_drogueria, seed_tercero_factory
):
    for i in range(5):
        seed_tercero_factory(razon_social=f"Tercero Paginado {i}")

    primera_pagina, total = listar_terceros_paginado(
        service_client, drogueria_id=seed_drogueria["id"], activo=None, page=1, page_size=2
    )
    segunda_pagina, _ = listar_terceros_paginado(
        service_client, drogueria_id=seed_drogueria["id"], activo=None, page=2, page_size=2
    )

    assert total == 5
    assert len(primera_pagina) == 2
    assert len(segunda_pagina) == 2
    assert {f["id"] for f in primera_pagina}.isdisjoint({f["id"] for f in segunda_pagina})


@pytest.mark.integration
def test_listar_terceros_paginado_filtro_rol_es_inclusivo_contra_postgres_real(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_cliente_factory, seed_rol_proveedor_factory
):
    """Bug preexistente (odd/tasks/terceros-listado-paginacion-y-rol.md):
    filtrar por rol='clientes' (o 'proveedores') usaba a excluir a un tercero
    que también tenía el otro rol. Esto prueba en vivo, contra PostgREST real,
    que el embed `!inner` server-side es inclusivo: el tercero con ambos
    roles tiene que aparecer filtrando por cualquiera de los dos."""
    ambos = seed_tercero_factory(razon_social="Ambos Roles Paginado SA")
    seed_rol_cliente_factory(ambos["id"])
    seed_rol_proveedor_factory(ambos["id"])

    items_clientes, total_clientes = listar_terceros_paginado(
        service_client, drogueria_id=seed_drogueria["id"], filtro_rol="clientes"
    )
    items_proveedores, total_proveedores = listar_terceros_paginado(
        service_client, drogueria_id=seed_drogueria["id"], filtro_rol="proveedores"
    )
    items_ambos, total_ambos = listar_terceros_paginado(
        service_client, drogueria_id=seed_drogueria["id"], filtro_rol="ambos"
    )

    assert ambos["id"] in {i["id"] for i in items_clientes}
    assert ambos["id"] in {i["id"] for i in items_proveedores}
    assert ambos["id"] in {i["id"] for i in items_ambos}
    assert total_clientes >= 1
    assert total_proveedores >= 1
    assert total_ambos >= 1


# ---------------------------------------------------------------------------
# 3.9 — actualizar el rol proveedor no afecta el rol cliente
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_actualizar_rol_proveedor_no_afecta_cliente(
    service_client,
    seed_drogueria,
    seed_tercero_factory,
    seed_rol_cliente_factory,
    seed_rol_proveedor_factory,
    seed_condicion_pago_factory,
):
    tercero = seed_tercero_factory()
    seed_rol_cliente_factory(tercero["id"], tipo="hospital")
    seed_rol_proveedor_factory(tercero["id"], tipo="laboratorio")
    condicion = seed_condicion_pago_factory()

    actualizado = actualizar_rol_proveedor(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProveedorRolUpdate(condicion_pago_id=condicion["id"]),
    )

    assert actualizado["condicion_pago_id"] == condicion["id"]

    cliente = obtener_rol_cliente(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
    )
    assert cliente["tipo"] == "hospital"
    assert cliente["condicion_pago_id"] is None


# ---------------------------------------------------------------------------
# 3.10 — actualizar identidad no toca los roles
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_actualizar_tercero_no_cambia_filas_de_rol(
    service_client, seed_drogueria, seed_usuario_sistema, seed_tercero_factory, seed_rol_cliente_factory
):
    tercero = seed_tercero_factory(razon_social="Droguería A")
    seed_rol_cliente_factory(tercero["id"], tipo="hospital")

    actualizado = actualizar_tercero(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroUpdate(nombre_fantasia="Droguería A Norte"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert actualizado["nombre_fantasia"] == "Droguería A Norte"
    assert actualizado["razon_social"] == "Droguería A"

    cliente = obtener_rol_cliente(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
    )
    assert cliente["tipo"] == "hospital"


# ---------------------------------------------------------------------------
# 3.11 — baja lógica (D4): `activo` lo escribe la importación
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_tercero_inactivo_no_aparece_en_el_listado_por_defecto(
    service_client, seed_drogueria, seed_tercero_factory
):
    activo = seed_tercero_factory(razon_social="Activo")
    inactivo = seed_tercero_factory(razon_social="Inactivo", activo=False)

    por_defecto = listar_terceros(service_client, drogueria_id=seed_drogueria["id"])
    assert {t["id"] for t in por_defecto} == {activo["id"]}

    todos = listar_terceros(service_client, drogueria_id=seed_drogueria["id"], activo=None)
    assert {t["id"] for t in todos} == {activo["id"], inactivo["id"]}


# ---------------------------------------------------------------------------
# 3.12 — aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_obtener_tercero_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    with pytest.raises(NotFoundError):
        obtener_tercero(service_client, tercero_id=tercero["id"], drogueria_id="otra-drogueria")


@pytest.mark.integration
def test_actualizar_tercero_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_usuario_sistema, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    with pytest.raises(NotFoundError):
        actualizar_tercero(
            service_client,
            tercero_id=tercero["id"],
            drogueria_id="otra-drogueria",
            body=TerceroUpdate(nombre_fantasia="Hackeado"),
            usuario_id=seed_usuario_sistema["id"],
        )


# ---------------------------------------------------------------------------
# 4.10 / 4.11 — condición/forma de pago habitual sobre los roles
# ---------------------------------------------------------------------------


def _condicion_de_otra_drogueria(service_client):
    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{uuid.uuid4().int % 99_999_999:08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": f"otra-terceros-{uuid.uuid4()}@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]
    condicion = service_client.table("condiciones_pago").insert(
        {"drogueria_id": otra_drogueria["id"], "nombre": f"Ajena {uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    return otra_drogueria, condicion


@pytest.mark.integration
def test_condicion_pago_habitual_de_otra_drogueria_lanza_validation_via_proveedor(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_proveedor_factory
):
    tercero = seed_tercero_factory()
    seed_rol_proveedor_factory(tercero["id"], tipo="laboratorio")
    otra_drogueria, condicion_ajena = _condicion_de_otra_drogueria(service_client)

    try:
        with pytest.raises(ValidationError):
            actualizar_rol_proveedor(
                service_client,
                tercero_id=tercero["id"],
                drogueria_id=seed_drogueria["id"],
                body=ProveedorRolUpdate(condicion_pago_id=condicion_ajena["id"]),
            )
        rol = obtener_rol_proveedor(
            service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
        )
        assert rol["condicion_pago_id"] is None
    finally:
        service_client.table("condiciones_pago").delete().eq("id", condicion_ajena["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_condicion_pago_habitual_de_otra_drogueria_lanza_validation_via_cliente(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_cliente_factory
):
    """Mismo caso que el de proveedor, por el rol cliente: _validar_condicion_y_forma_pago
    se comporta igual en los dos caminos (tasks.md Phase 12, task 12.1)."""
    tercero = seed_tercero_factory()
    seed_rol_cliente_factory(tercero["id"], tipo="hospital")
    otra_drogueria, condicion_ajena = _condicion_de_otra_drogueria(service_client)

    try:
        with pytest.raises(ValidationError):
            actualizar_rol_cliente(
                service_client,
                tercero_id=tercero["id"],
                drogueria_id=seed_drogueria["id"],
                body=ClienteRolUpdate(condicion_pago_id=condicion_ajena["id"]),
            )
        rol = obtener_rol_cliente(
            service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
        )
        assert rol["condicion_pago_id"] is None
    finally:
        service_client.table("condiciones_pago").delete().eq("id", condicion_ajena["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_asignar_condicion_y_forma_pago_habitual_a_un_cliente(
    service_client,
    seed_drogueria,
    seed_tercero_factory,
    seed_rol_cliente_factory,
    seed_condicion_pago_factory,
    seed_forma_pago_factory,
):
    tercero = seed_tercero_factory()
    seed_rol_cliente_factory(tercero["id"], tipo="hospital")
    condicion = seed_condicion_pago_factory(plazos_dias=[30, 60, 90])
    forma = seed_forma_pago_factory(tipo="transferencia")

    cliente = actualizar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolUpdate(condicion_pago_id=condicion["id"], forma_pago_id=forma["id"]),
    )

    assert cliente["condicion_pago_id"] == condicion["id"]
    assert cliente["forma_pago_id"] == forma["id"]
    assert cliente["tipo"] == "hospital"


# ---------------------------------------------------------------------------
# Fase 7/8 — rol + tercero combinados, consumidos por services.terceros.api
# (services/presupuestacion/clientes/ y catalogo/ ya no leen `clientes`/
# `proveedores` directamente, ver design.md D5).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listar_clientes_con_tercero_incluye_identidad_embebida(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_cliente_factory
):
    tercero = seed_tercero_factory(razon_social="Hospital Combinado")
    seed_rol_cliente_factory(tercero["id"], tipo="hospital")

    filas = listar_clientes_con_tercero(service_client, drogueria_id=seed_drogueria["id"])

    assert len(filas) == 1
    assert filas[0]["id"] == tercero["id"]
    assert filas[0]["terceros"]["razon_social"] == "Hospital Combinado"


@pytest.mark.integration
def test_listar_clientes_con_tercero_filtra_por_activo(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_cliente_factory
):
    activo = seed_tercero_factory(razon_social="Activo")
    inactivo = seed_tercero_factory(razon_social="Inactivo")
    seed_rol_cliente_factory(activo["id"], tipo="hospital")
    seed_rol_cliente_factory(inactivo["id"], tipo="hospital", activo=False)

    solo_activos = listar_clientes_con_tercero(
        service_client, drogueria_id=seed_drogueria["id"], activo=True
    )
    assert {f["id"] for f in solo_activos} == {activo["id"]}


@pytest.mark.integration
def test_obtener_cliente_con_tercero_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_cliente_factory
):
    tercero = seed_tercero_factory()
    seed_rol_cliente_factory(tercero["id"], tipo="hospital")

    with pytest.raises(NotFoundError):
        obtener_cliente_con_tercero(
            service_client, tercero_id=tercero["id"], drogueria_id="otra-drogueria"
        )


@pytest.mark.integration
def test_listar_proveedores_con_tercero_incluye_identidad_embebida(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_proveedor_factory
):
    tercero = seed_tercero_factory(razon_social="Laboratorio Combinado")
    seed_rol_proveedor_factory(tercero["id"], tipo="laboratorio")

    filas = listar_proveedores_con_tercero(service_client, drogueria_id=seed_drogueria["id"])

    assert len(filas) == 1
    assert filas[0]["id"] == tercero["id"]
    assert filas[0]["terceros"]["razon_social"] == "Laboratorio Combinado"


@pytest.mark.integration
def test_tercero_inactivo_no_aparece_en_clientes_ni_proveedores_aunque_el_rol_siga_activo(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_cliente_factory, seed_rol_proveedor_factory
):
    """Post-verify fix (verify-report.md CRITICAL finding, terceros-identidad spec
    "Deactivation semantics apply consistently"): an inactive tercero must be hidden
    from listar_clientes_con_tercero/listar_proveedores_con_tercero even when the role
    row's own `activo` column is still true. `terceros.activo` is written by the import,
    so the test seeds it directly."""
    tercero = seed_tercero_factory(razon_social="Con ambos roles", activo=False)
    seed_rol_cliente_factory(tercero["id"], tipo="hospital")
    seed_rol_proveedor_factory(tercero["id"], tipo="laboratorio")

    fila_cliente = (
        service_client.table("clientes").select("activo").eq("id", tercero["id"]).execute().data[0]
    )
    fila_proveedor = (
        service_client.table("proveedores").select("activo").eq("id", tercero["id"]).execute().data[0]
    )
    assert fila_cliente["activo"] is True
    assert fila_proveedor["activo"] is True

    clientes_activos = listar_clientes_con_tercero(service_client, drogueria_id=seed_drogueria["id"])
    proveedores_activos = listar_proveedores_con_tercero(
        service_client, drogueria_id=seed_drogueria["id"]
    )

    assert tercero["id"] not in {f["id"] for f in clientes_activos}
    assert tercero["id"] not in {f["id"] for f in proveedores_activos}


@pytest.mark.integration
def test_obtener_proveedor_con_tercero_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_proveedor_factory
):
    tercero = seed_tercero_factory()
    seed_rol_proveedor_factory(tercero["id"], tipo="laboratorio")

    with pytest.raises(NotFoundError):
        obtener_proveedor_con_tercero(
            service_client, tercero_id=tercero["id"], drogueria_id="otra-drogueria"
        )


# ---------------------------------------------------------------------------
# 12.2 — Referential Compatibility (terceros-identidad spec.md, post-verify
# follow-up): preexisting FKs to clientes.id keep resolving unchanged, because
# clientes.id is the same shared primary key as terceros.id (D1) — no data
# migration of procesos_comerciales was required by the terceros-modelo
# migration.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_procesos_comerciales_cliente_id_resuelve_sin_migracion_de_datos(
    service_client, seed_drogueria, seed_tercero_factory, seed_rol_cliente_factory
):
    tercero = seed_tercero_factory(razon_social="Cliente con proceso comercial")
    seed_rol_cliente_factory(tercero["id"], tipo="hospital")

    proceso = (
        service_client.table("procesos_comerciales")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "cliente_id": tercero["id"],
                "clase": "cotizacion",
                "nombre": "Proceso referencial de test",
            }
        )
        .execute()
        .data[0]
    )

    try:
        fila = (
            service_client.table("procesos_comerciales")
            .select("id, clientes(id)")
            .eq("id", proceso["id"])
            .execute()
            .data[0]
        )
        assert fila["clientes"]["id"] == tercero["id"]
    finally:
        service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()
