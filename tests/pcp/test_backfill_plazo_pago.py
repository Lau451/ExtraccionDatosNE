"""Integración (tasks.md 2.15, design.md D5): el backfill de
precios_proveedor.condicion_pago_id crea exactamente una fila de
condiciones_pago por cada valor distinto de plazo_pago_dias, por drogueria_id,
y las dos vistas recreadas por 0012_pcp_extras.sql (v_precios_especiales_vigentes,
v_presupuesto_revision) siguen resolviendo despues del cambio.

Corre contra el backfill como función nombrada e idempotente
(backfill_condicion_pago_desde_plazo, migración 0012 M5b) en vez de contra el
DO block de la migración en sí -- así el test puede invocarlo de nuevo sobre
datos sembrados en el momento del test, sin depender de que su ejecución
coincida con el momento real en que 0012_pcp_extras.sql se aplicó al proyecto
de test (ver comentario de diseño en la propia migración, sección M5b).

Requiere que 0012_pcp_extras.sql ya esté aplicada al proyecto de test
(tasks.md 2.14); si la función/columnas no existen todavía, estos tests
fallan con un APIError de PostgREST -- señal esperada mientras 2.14 sigue
pendiente (ver tasks.md).
"""

import uuid
from datetime import date, timedelta

import pytest


@pytest.fixture
def seed_precio_proveedor_factory(service_client, seed_drogueria, seed_producto, seed_proveedor_pcp):
    creados: list[str] = []

    def _seed(*, plazo_pago_dias: int | None):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "proveedor_id": seed_proveedor_pcp["id"],
            "producto_id": seed_producto["id"],
            "precio_unitario": "10.00",
            "mantenimiento_hasta": (date.today() + timedelta(days=30)).isoformat(),
            "plazo_pago_dias": plazo_pago_dias,
        }
        fila_pp = service_client.table("precios_proveedor").insert(fila).execute().data[0]
        creados.append(fila_pp["id"])
        return fila_pp

    yield _seed
    for precio_id in creados:
        service_client.table("precios_proveedor").delete().eq("id", precio_id).execute()


@pytest.mark.integration
def test_backfill_crea_una_condicion_pago_por_plazo_distinto(
    service_client, seed_drogueria, seed_precio_proveedor_factory
):
    drogueria_id = seed_drogueria["id"]
    precio_30 = seed_precio_proveedor_factory(plazo_pago_dias=30)
    precio_45 = seed_precio_proveedor_factory(plazo_pago_dias=45)
    # Mismo plazo que precio_30: no debe crear una segunda condiciones_pago para 30.
    precio_30_bis = seed_precio_proveedor_factory(plazo_pago_dias=30)

    condiciones_creadas: list[str] = []
    try:
        resultado = service_client.rpc(
            "backfill_condicion_pago_desde_plazo", {"p_drogueria_id": drogueria_id}
        ).execute()
        assert resultado.data == 3, (
            "El backfill debe actualizar las 3 filas de precios_proveedor sembradas"
        )

        condiciones = (
            service_client.table("condiciones_pago")
            .select("id, nombre, plazos_dias")
            .eq("drogueria_id", drogueria_id)
            .in_("nombre", ["30 dias", "45 dias"])
            .execute()
            .data
        )
        condiciones_creadas = [c["id"] for c in condiciones]

        assert len(condiciones) == 2, (
            "Debe existir exactamente una condiciones_pago por valor distinto de "
            f"plazo_pago_dias (30, 45), no {len(condiciones)}"
        )
        por_nombre = {c["nombre"]: c for c in condiciones}
        assert por_nombre["30 dias"]["plazos_dias"] == [30]
        assert por_nombre["45 dias"]["plazos_dias"] == [45]

        filas_pp = (
            service_client.table("precios_proveedor")
            .select("id, plazo_pago_dias, condicion_pago_id")
            .in_("id", [precio_30["id"], precio_45["id"], precio_30_bis["id"]])
            .execute()
            .data
        )
        por_id = {f["id"]: f for f in filas_pp}
        assert por_id[precio_30["id"]]["condicion_pago_id"] == por_nombre["30 dias"]["id"]
        assert por_id[precio_45["id"]]["condicion_pago_id"] == por_nombre["45 dias"]["id"]
        # El segundo precio con plazo 30 reusa la MISMA condicion_pago (find-or-create).
        assert por_id[precio_30_bis["id"]]["condicion_pago_id"] == por_nombre["30 dias"]["id"]

        # Idempotencia: re-invocar no crea condiciones duplicadas ni vuelve a
        # "actualizar" filas ya backfilleadas (guarda condicion_pago_id IS NULL).
        segunda_pasada = service_client.rpc(
            "backfill_condicion_pago_desde_plazo", {"p_drogueria_id": drogueria_id}
        ).execute()
        assert segunda_pasada.data == 0
        condiciones_segunda = (
            service_client.table("condiciones_pago")
            .select("id")
            .eq("drogueria_id", drogueria_id)
            .in_("nombre", ["30 dias", "45 dias"])
            .execute()
            .data
        )
        assert len(condiciones_segunda) == 2
    finally:
        for condicion_id in condiciones_creadas:
            service_client.table("condiciones_pago").delete().eq("id", condicion_id).execute()


@pytest.mark.integration
def test_backfill_ignora_otras_droguerias(
    service_client, seed_drogueria, seed_precio_proveedor_factory
):
    """El backfill scoped a p_drogueria_id no toca precios_proveedor de otra
    drogueria (aislamiento por tenant, no solo por RLS)."""
    otra_drogueria = (
        service_client.table("droguerias")
        .insert(
            {
                "nombre": "Otra Droguería Test",
                "razon_social": "Otra Droguería Test SA",
                "cuit": f"20-{uuid.uuid4().int % 99_999_999:08d}-9",
                "ciudad": "Rosario",
                "provincia": "Santa Fe",
                "contacto_email": f"seed-{uuid.uuid4()}@seed.local",
                "contacto_telefono": "0000000000",
            }
        )
        .execute()
        .data[0]
    )
    try:
        precio_otra = seed_precio_proveedor_factory(plazo_pago_dias=60)
        # Fuerza el precio a pertenecer a la otra drogueria (el fixture usa seed_drogueria).
        service_client.table("precios_proveedor").update(
            {"drogueria_id": otra_drogueria["id"]}
        ).eq("id", precio_otra["id"]).execute()

        resultado = service_client.rpc(
            "backfill_condicion_pago_desde_plazo", {"p_drogueria_id": seed_drogueria["id"]}
        ).execute()
        assert resultado.data == 0

        fila = (
            service_client.table("precios_proveedor")
            .select("condicion_pago_id")
            .eq("id", precio_otra["id"])
            .single()
            .execute()
            .data
        )
        assert fila["condicion_pago_id"] is None
    finally:
        service_client.table("condiciones_pago").delete().eq(
            "drogueria_id", otra_drogueria["id"]
        ).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_v_precios_especiales_vigentes_resuelve_con_plazo_backfilleado(
    service_client, seed_drogueria, seed_precio_proveedor_factory
):
    precio = seed_precio_proveedor_factory(plazo_pago_dias=30)
    condiciones_creadas: list[str] = []
    try:
        service_client.table("precios_proveedor").update({"activa": True}).eq(
            "id", precio["id"]
        ).execute()
        service_client.rpc(
            "backfill_condicion_pago_desde_plazo", {"p_drogueria_id": seed_drogueria["id"]}
        ).execute()
        condiciones_creadas = [
            c["id"]
            for c in service_client.table("condiciones_pago")
            .select("id")
            .eq("drogueria_id", seed_drogueria["id"])
            .eq("nombre", "30 dias")
            .execute()
            .data
        ]

        fila_vista = (
            service_client.table("v_precios_especiales_vigentes")
            .select("precio_proveedor_id, plazo_pago_dias")
            .eq("precio_proveedor_id", precio["id"])
            .single()
            .execute()
            .data
        )
        assert fila_vista["plazo_pago_dias"] == 30
    finally:
        for condicion_id in condiciones_creadas:
            service_client.table("condiciones_pago").delete().eq("id", condicion_id).execute()


@pytest.mark.integration
def test_v_presupuesto_revision_resuelve_sin_error(service_client, seed_drogueria):
    """Chequeo liviano de resolución (no de valores): tras el DROP+CREATE de
    0012, la vista debe seguir siendo consultable sin error de SQL. La
    cobertura semántica profunda de plazo_pago_proveedor vive en
    tests/pricing (requiere el andamiaje completo de presupuesto/proceso)."""
    respuesta = (
        service_client.table("v_presupuesto_revision")
        .select("presupuesto_id, plazo_pago_proveedor")
        .limit(1)
        .execute()
    )
    assert isinstance(respuesta.data, list)
