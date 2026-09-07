import pytest


@pytest.fixture
def seed_pcp_factory(service_client, seed_drogueria, seed_proceso_comercial):
    """Crea una fila mínima de `pcp` (0011_pcp_modelo.sql M1) para tests que
    solo necesitan un `pcp_id`/`drogueria_id` válido como referente (p.ej.
    pcp-historial, PR3) -- no pasa por services/pcp/gestion porque ese módulo
    todavía no existe (llega en PR4). `pcp.presupuesto_id`/`proceso_comercial_id`
    son NOT NULL, así que arma también un `presupuesto` mínimo por fila.
    """
    creados: list[tuple[dict, dict]] = []

    def _seed(**overrides):
        presupuesto = (
            service_client.table("presupuestos")
            .insert(
                {
                    "proceso_comercial_id": seed_proceso_comercial["id"],
                    "drogueria_id": seed_drogueria["id"],
                    "estado": "generado",
                    "monto_total": "0",
                    "cantidad_items": 0,
                    "items_sin_precio": 0,
                }
            )
            .execute()
            .data[0]
        )
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "presupuesto_id": presupuesto["id"],
            "proceso_comercial_id": seed_proceso_comercial["id"],
            **overrides,
        }
        pcp = service_client.table("pcp").insert(fila).execute().data[0]
        creados.append((pcp, presupuesto))
        return pcp

    yield _seed
    for pcp, presupuesto in creados:
        # fk_pcph_pcp (pcp_historial -> pcp) es ON DELETE CASCADE
        # (0012_pcp_extras.sql M1): borrar `pcp` alcanza para limpiar sus
        # eventos de historial sin un DELETE explícito.
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("presupuestos").delete().eq("id", presupuesto["id"]).execute()


@pytest.fixture
def limpiar_pcp_terceros(service_client, seed_drogueria):
    """proveedores es una tabla de rol cuyo id comparte identidad con terceros
    (0008_terceros_modelo.sql, fk_prov_tercero ON DELETE CASCADE) -- borrar
    terceros alcanza para limpiar la fila de proveedores asociada. Mismo
    criterio que tests/terceros/conftest.py::limpiar_terceros."""
    yield
    service_client.table("terceros").delete().eq("drogueria_id", seed_drogueria["id"]).execute()


@pytest.fixture
def seed_proveedor_pcp(service_client, seed_drogueria, limpiar_pcp_terceros):
    """Reemplazo local de tests/conftest.py::seed_proveedor (raíz) para los
    tests de tests/pcp/. Ese fixture compartido inserta razon_social
    directamente en `proveedores` -- columna que 0008_terceros_modelo.sql
    movió a `terceros`, por lo que está roto (PGRST204 "Could not find the
    'razon_social' column of 'proveedores'") para cualquier consumidor desde
    esa migración. Bug preexistente, no introducido por gestor-pcp; reportado
    en tasks.md/el resumen de esta PR en vez de corregirse en tests/conftest.py
    (afecta módulos fuera del alcance de esta fase). proveedores.id comparte
    identidad con terceros.id (fk_prov_tercero), así que el alta va en dos
    pasos: primero terceros, después proveedores con el mismo id."""
    tercero = (
        service_client.table("terceros")
        .insert({"drogueria_id": seed_drogueria["id"], "razon_social": "Proveedor PCP Test"})
        .execute()
        .data[0]
    )
    proveedor = (
        service_client.table("proveedores")
        .insert(
            {
                "id": tercero["id"],
                "drogueria_id": seed_drogueria["id"],
                "es_proveedor_compra": True,
            }
        )
        .execute()
        .data[0]
    )
    return proveedor
