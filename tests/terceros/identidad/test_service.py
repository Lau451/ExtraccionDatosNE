import uuid

import pytest

from services.shared.exceptions import ConflictError, NotFoundError, ValidationError
from services.terceros.identidad.models import (
    ClienteRolCreate,
    ClienteRolUpdate,
    ProveedorRolCreate,
    ProveedorRolUpdate,
    TerceroCreate,
    TerceroUpdate,
)
from services.terceros.identidad.service import (
    actualizar_rol_cliente,
    actualizar_rol_proveedor,
    actualizar_tercero,
    asignar_rol_cliente,
    asignar_rol_proveedor,
    crear_tercero,
    listar_clientes_con_tercero,
    listar_proveedores_con_tercero,
    listar_terceros,
    obtener_cliente_con_tercero,
    obtener_proveedor_con_tercero,
    obtener_rol_cliente,
    obtener_rol_proveedor,
    obtener_tercero,
)


def _codigo() -> str:
    return f"TER-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# 3.4 / 3.5 — creación e idempotencia de codigo_interno
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_tercero_con_codigo_interno_y_nombre(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_terceros
):
    codigo = _codigo()

    resultado = crear_tercero(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=TerceroCreate(codigo_interno=codigo, razon_social="Droguería del Sur SA"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["codigo_interno"] == codigo
    assert resultado["razon_social"] == "Droguería del Sur SA"
    assert resultado["activo"] is True


@pytest.mark.integration
def test_crear_tercero_codigo_interno_duplicado_lanza_conflict(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_terceros
):
    codigo = _codigo()
    crear_tercero(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=TerceroCreate(codigo_interno=codigo, razon_social="Original"),
        usuario_id=seed_usuario_sistema["id"],
    )

    with pytest.raises(ConflictError):
        crear_tercero(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=TerceroCreate(codigo_interno=codigo, razon_social="Duplicado"),
            usuario_id=seed_usuario_sistema["id"],
        )

    todos = listar_terceros(service_client, drogueria_id=seed_drogueria["id"], activo=None)
    assert len([t for t in todos if t["codigo_interno"] == codigo]) == 1


# ---------------------------------------------------------------------------
# 3.6 / 3.7 / 3.8 — asignación de roles
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_asignar_ambos_roles_al_mismo_tercero(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()

    cliente = asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )
    proveedor = asignar_rol_proveedor(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProveedorRolCreate(tipo="laboratorio"),
    )

    assert cliente["id"] == tercero["id"]
    assert proveedor["id"] == tercero["id"]

    encontrado_cliente = obtener_rol_cliente(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
    )
    encontrado_proveedor = obtener_rol_proveedor(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
    )
    assert encontrado_cliente["id"] == tercero["id"]
    assert encontrado_proveedor["id"] == tercero["id"]


@pytest.mark.integration
def test_asignar_un_solo_rol_no_crea_el_otro(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()

    asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )

    with pytest.raises(NotFoundError):
        obtener_rol_proveedor(
            service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
        )


@pytest.mark.integration
def test_asignar_rol_duplicado_lanza_conflict(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )

    with pytest.raises(ConflictError):
        asignar_rol_cliente(
            service_client,
            tercero_id=tercero["id"],
            drogueria_id=seed_drogueria["id"],
            body=ClienteRolCreate(tipo="municipio"),
        )

    encontrado = obtener_rol_cliente(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
    )
    assert encontrado["tipo"] == "hospital"


# ---------------------------------------------------------------------------
# 3.9 — es_competidor/es_proveedor_compra no afectan el rol cliente
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_actualizar_flags_proveedor_no_afecta_cliente(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )
    asignar_rol_proveedor(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProveedorRolCreate(tipo="laboratorio", es_competidor=False, es_proveedor_compra=False),
    )

    actualizado = actualizar_rol_proveedor(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProveedorRolUpdate(es_competidor=True, es_proveedor_compra=True),
    )

    assert actualizado["es_competidor"] is True
    assert actualizado["es_proveedor_compra"] is True

    cliente = obtener_rol_cliente(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
    )
    assert cliente["tipo"] == "hospital"


# ---------------------------------------------------------------------------
# 3.10 — actualizar identidad no toca los roles
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_actualizar_tercero_no_cambia_filas_de_rol(
    service_client, seed_drogueria, seed_usuario_sistema, seed_tercero_factory
):
    tercero = seed_tercero_factory(razon_social="Droguería A")
    asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )

    actualizado = actualizar_tercero(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroUpdate(razon_social="Droguería A S.A."),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert actualizado["razon_social"] == "Droguería A S.A."

    cliente = obtener_rol_cliente(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"]
    )
    assert cliente["tipo"] == "hospital"


# ---------------------------------------------------------------------------
# 3.11 — baja lógica (D4)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_desactivar_tercero_lo_oculta_del_listado_por_defecto(
    service_client, seed_drogueria, seed_usuario_sistema, seed_tercero_factory
):
    activo = seed_tercero_factory(razon_social="Activo")
    a_desactivar = seed_tercero_factory(razon_social="A desactivar")

    actualizar_tercero(
        service_client,
        tercero_id=a_desactivar["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroUpdate(activo=False),
        usuario_id=seed_usuario_sistema["id"],
    )

    por_defecto = listar_terceros(service_client, drogueria_id=seed_drogueria["id"])
    assert {t["id"] for t in por_defecto} == {activo["id"]}

    todos = listar_terceros(service_client, drogueria_id=seed_drogueria["id"], activo=None)
    assert {t["id"] for t in todos} == {activo["id"], a_desactivar["id"]}

    fila = (
        service_client.table("terceros").select("activo").eq("id", a_desactivar["id"]).execute().data[0]
    )
    assert fila["activo"] is False


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
            body=TerceroUpdate(razon_social="Hackeado"),
            usuario_id=seed_usuario_sistema["id"],
        )


# ---------------------------------------------------------------------------
# 4.10 / 4.11 — condición/forma de pago habitual sobre los roles
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_asignar_condicion_pago_habitual_de_otra_drogueria_lanza_validation(
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
            "contacto_email": f"otra-terceros-{uuid.uuid4()}@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]
    condicion_ajena = service_client.table("condiciones_pago").insert(
        {"drogueria_id": otra_drogueria["id"], "nombre": f"Ajena {uuid.uuid4().hex[:8]}"}
    ).execute().data[0]

    try:
        with pytest.raises(ValidationError):
            asignar_rol_proveedor(
                service_client,
                tercero_id=tercero["id"],
                drogueria_id=seed_drogueria["id"],
                body=ProveedorRolCreate(
                    tipo="laboratorio", condicion_pago_id=condicion_ajena["id"]
                ),
            )
    finally:
        service_client.table("condiciones_pago").delete().eq("id", condicion_ajena["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_asignar_condicion_pago_habitual_de_otra_drogueria_lanza_validation_via_cliente(
    service_client, seed_drogueria, seed_tercero_factory
):
    """Mirror of test_asignar_condicion_pago_habitual_de_otra_drogueria_lanza_validation
    (above) via asignar_rol_cliente instead of asignar_rol_proveedor. Post-verify follow-up
    (tasks.md Phase 12, task 12.1): verify-report.md WARNING #1 named the wrong path as
    missing — the proveedor path was already covered by the test above; this confirms
    _validar_condicion_y_forma_pago behaves identically on the cliente path too, not just
    by code inspection."""
    tercero = seed_tercero_factory()
    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{uuid.uuid4().int % 99_999_999:08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": f"otra-terceros-cliente-{uuid.uuid4()}@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]
    condicion_ajena = service_client.table("condiciones_pago").insert(
        {"drogueria_id": otra_drogueria["id"], "nombre": f"Ajena {uuid.uuid4().hex[:8]}"}
    ).execute().data[0]

    try:
        with pytest.raises(ValidationError):
            asignar_rol_cliente(
                service_client,
                tercero_id=tercero["id"],
                drogueria_id=seed_drogueria["id"],
                body=ClienteRolCreate(
                    tipo="hospital", condicion_pago_id=condicion_ajena["id"]
                ),
            )
    finally:
        service_client.table("condiciones_pago").delete().eq("id", condicion_ajena["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_asignar_condicion_y_forma_pago_habitual_a_un_cliente(
    service_client, seed_drogueria, seed_tercero_factory, seed_condicion_pago_factory, seed_forma_pago_factory
):
    tercero = seed_tercero_factory()
    condicion = seed_condicion_pago_factory(plazos_dias=[30, 60, 90])
    forma = seed_forma_pago_factory(tipo="transferencia")

    cliente = asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(
            tipo="hospital", condicion_pago_id=condicion["id"], forma_pago_id=forma["id"]
        ),
    )

    assert cliente["condicion_pago_id"] == condicion["id"]
    assert cliente["forma_pago_id"] == forma["id"]


# ---------------------------------------------------------------------------
# Fase 7/8 — rol + tercero combinados, consumidos por services.terceros.api
# (services/presupuestacion/clientes/ y catalogo/ ya no leen `clientes`/
# `proveedores` directamente, ver design.md D5).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listar_clientes_con_tercero_incluye_identidad_embebida(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory(razon_social="Hospital Combinado")
    asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )

    filas = listar_clientes_con_tercero(service_client, drogueria_id=seed_drogueria["id"])

    assert len(filas) == 1
    assert filas[0]["id"] == tercero["id"]
    assert filas[0]["terceros"]["razon_social"] == "Hospital Combinado"


@pytest.mark.integration
def test_listar_clientes_con_tercero_filtra_por_activo(
    service_client, seed_drogueria, seed_tercero_factory
):
    activo = seed_tercero_factory(razon_social="Activo")
    inactivo = seed_tercero_factory(razon_social="Inactivo")
    asignar_rol_cliente(
        service_client, tercero_id=activo["id"], drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )
    asignar_rol_cliente(
        service_client, tercero_id=inactivo["id"], drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )
    actualizar_rol_cliente(
        service_client, tercero_id=inactivo["id"], drogueria_id=seed_drogueria["id"],
        body=ClienteRolUpdate(activo=False),
    )

    solo_activos = listar_clientes_con_tercero(
        service_client, drogueria_id=seed_drogueria["id"], activo=True
    )
    assert {f["id"] for f in solo_activos} == {activo["id"]}


@pytest.mark.integration
def test_obtener_cliente_con_tercero_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    asignar_rol_cliente(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )

    with pytest.raises(NotFoundError):
        obtener_cliente_con_tercero(
            service_client, tercero_id=tercero["id"], drogueria_id="otra-drogueria"
        )


@pytest.mark.integration
def test_listar_proveedores_con_tercero_incluye_identidad_embebida(
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory(razon_social="Laboratorio Combinado")
    asignar_rol_proveedor(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProveedorRolCreate(tipo="laboratorio"),
    )

    filas = listar_proveedores_con_tercero(service_client, drogueria_id=seed_drogueria["id"])

    assert len(filas) == 1
    assert filas[0]["id"] == tercero["id"]
    assert filas[0]["terceros"]["razon_social"] == "Laboratorio Combinado"


@pytest.mark.integration
def test_desactivar_tercero_lo_oculta_de_clientes_y_proveedores_aunque_el_rol_siga_activo(
    service_client, seed_drogueria, seed_usuario_sistema, seed_tercero_factory
):
    """Post-verify fix (verify-report.md CRITICAL finding, terceros-identidad spec
    "Deactivation semantics apply consistently"): deactivating the tercero itself must
    hide it from listar_clientes_con_tercero/listar_proveedores_con_tercero even when
    the role row's own `activo` column was never touched."""
    tercero = seed_tercero_factory(razon_social="Con ambos roles")
    asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )
    asignar_rol_proveedor(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProveedorRolCreate(tipo="laboratorio"),
    )

    actualizar_tercero(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=TerceroUpdate(activo=False),
        usuario_id=seed_usuario_sistema["id"],
    )

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
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory()
    asignar_rol_proveedor(
        service_client, tercero_id=tercero["id"], drogueria_id=seed_drogueria["id"],
        body=ProveedorRolCreate(tipo="laboratorio"),
    )

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
    service_client, seed_drogueria, seed_tercero_factory
):
    tercero = seed_tercero_factory(razon_social="Cliente con proceso comercial")
    asignar_rol_cliente(
        service_client,
        tercero_id=tercero["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteRolCreate(tipo="hospital"),
    )

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
