"""8.3-8.7a (openspec/changes/gestor-pcp/tasks.md Fase 8) -- pcp-legacy-import:
idempotencia por `codigo_legacy`, trazabilidad vía `pcp_legacy_map`, origen
`import_legado` en los renglones, y coexistencia con un PCP creado
nativamente (spec `pcp-legacy-import`).

RED hasta que 8.2/8.8 creen `services/pcp/imports/{repository,service}.py`.
"""

from decimal import Decimal

import pytest

from services.pcp.imports.models import FilaImportPcpLegacy
from services.pcp.imports.service import importar_pcp_legacy


def _limpiar_import(service_client, *, pcp_id: str, presupuesto_id: str, proceso_comercial_id: str) -> None:
    """Orden obligatorio (RESTRICT sin CASCADE entre presupuestos/procesos_
    comerciales): borrar `pcp` primero cascadea `pcp_renglones`/
    `pcp_legacy_map`/`pcp_historial` (fk_pcpr_pcp/fk_pcplm_pcp/fk_pcph_pcp),
    liberando la referencia que bloquearía el CASCADE de `items_proceso` al
    borrar `procesos_comerciales` (fk_ip_proc)."""
    service_client.table("pcp").delete().eq("id", pcp_id).execute()
    service_client.table("presupuestos").delete().eq("id", presupuesto_id).execute()
    service_client.table("procesos_comerciales").delete().eq("id", proceso_comercial_id).execute()


def _fila(*, codigo_cliente: str, numero_pcp: str, renglon: int = 1, **overrides) -> FilaImportPcpLegacy:
    base = {
        "codigo_cliente": codigo_cliente,
        "razon_social_cliente": "Hospital Import Test",
        "numero_pcp": numero_pcp,
        "renglon": renglon,
        "descripcion_producto": f"Producto renglón {renglon}",
        "cantidad_producto": Decimal("10"),
        **overrides,
    }
    return FilaImportPcpLegacy(**base)


# ---------------------------------------------------------------------------
# 8.3 -- reimportar el mismo codigo_legacy actualiza el PCP existente
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reimportar_mismo_codigo_actualiza_el_pcp_existente_sin_duplicarlo(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-2001")
    fila = _fila(codigo_cliente="CLI-2001", numero_pcp="PCP-2001")

    resultado_1 = importar_pcp_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        resultado_2 = importar_pcp_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )

        assert resultado_1[0]["accion"] == "creado"
        assert resultado_2[0]["accion"] == "actualizado"
        assert resultado_1[0]["pcp_id"] == resultado_2[0]["pcp_id"]
    finally:
        pcp = service_client.table("pcp").select("*").eq("id", resultado_1[0]["pcp_id"]).execute().data[0]
        _limpiar_import(
            service_client,
            pcp_id=pcp["id"],
            presupuesto_id=pcp["presupuesto_id"],
            proceso_comercial_id=pcp["proceso_comercial_id"],
        )


# ---------------------------------------------------------------------------
# 8.4 -- reimportar no duplica el renglón matcheado
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reimportar_no_duplica_el_renglon_matcheado(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-2002")
    fila = _fila(codigo_cliente="CLI-2002", numero_pcp="PCP-2002")

    resultado_1 = importar_pcp_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        importar_pcp_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )

        renglones = (
            service_client.table("pcp_renglones")
            .select("id")
            .eq("pcp_id", resultado_1[0]["pcp_id"])
            .execute()
            .data
        )
        assert len(renglones) == 1
    finally:
        pcp = service_client.table("pcp").select("*").eq("id", resultado_1[0]["pcp_id"]).execute().data[0]
        _limpiar_import(
            service_client,
            pcp_id=pcp["id"],
            presupuesto_id=pcp["presupuesto_id"],
            proceso_comercial_id=pcp["proceso_comercial_id"],
        )


# ---------------------------------------------------------------------------
# 8.5 -- pcp_legacy_map: una fila en el primer import, ninguna adicional al reimportar
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_pcp_legacy_map_se_crea_una_vez_y_no_se_duplica_al_reimportar(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-3001")
    fila = _fila(codigo_cliente="CLI-3001", numero_pcp="PCP-3001")

    resultado_1 = importar_pcp_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        mapa_tras_primer_import = (
            service_client.table("pcp_legacy_map")
            .select("pcp_id")
            .eq("drogueria_id", seed_drogueria["id"])
            .eq("codigo_legacy", "PCP-3001")
            .execute()
            .data
        )
        assert len(mapa_tras_primer_import) == 1
        assert mapa_tras_primer_import[0]["pcp_id"] == resultado_1[0]["pcp_id"]

        importar_pcp_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )

        mapa_tras_reimport = (
            service_client.table("pcp_legacy_map")
            .select("pcp_id")
            .eq("drogueria_id", seed_drogueria["id"])
            .eq("codigo_legacy", "PCP-3001")
            .execute()
            .data
        )
        assert len(mapa_tras_reimport) == 1
    finally:
        pcp = service_client.table("pcp").select("*").eq("id", resultado_1[0]["pcp_id"]).execute().data[0]
        _limpiar_import(
            service_client,
            pcp_id=pcp["id"],
            presupuesto_id=pcp["presupuesto_id"],
            proceso_comercial_id=pcp["proceso_comercial_id"],
        )


# ---------------------------------------------------------------------------
# 8.6 -- el renglón importado lleva origen = 'import_legado'
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_renglon_importado_lleva_origen_import_legado(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-4001")
    fila = _fila(codigo_cliente="CLI-4001", numero_pcp="PCP-4101")

    resultado = importar_pcp_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        renglon = (
            service_client.table("pcp_renglones")
            .select("origen")
            .eq("pcp_id", resultado[0]["pcp_id"])
            .execute()
            .data[0]
        )
        assert renglon["origen"] == "import_legado"
    finally:
        pcp = service_client.table("pcp").select("*").eq("id", resultado[0]["pcp_id"]).execute().data[0]
        _limpiar_import(
            service_client,
            pcp_id=pcp["id"],
            presupuesto_id=pcp["presupuesto_id"],
            proceso_comercial_id=pcp["proceso_comercial_id"],
        )


# ---------------------------------------------------------------------------
# 8.7 -- un PCP creado nativamente, luego matcheado por codigo_legacy, se
# actualiza en vez de duplicarse
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_import_actualiza_un_pcp_creado_nativamente_sin_duplicarlo(
    service_client, seed_drogueria, seed_usuario_sistema, seed_pcp_factory
):
    pcp_nativo = seed_pcp_factory()
    # "un PCP creado por API y luego asignado codigo_legacy" -- no hay
    # endpoint dedicado para esa asignación todavía, se simula con el mismo
    # insert que hace `pcp_legacy_map` en un primer import real.
    service_client.table("pcp_legacy_map").insert(
        {"pcp_id": pcp_nativo["id"], "drogueria_id": seed_drogueria["id"], "codigo_legacy": "PCP-5001"}
    ).execute()

    # codigo_cliente deliberadamente irresoluble: en la rama de reimport
    # nunca se llega a `_resolver_cliente_id` (D8, "procesos_comerciales /
    # presupuestos NUNCA se tocan de nuevo") -- si el import intentara crear
    # un placeholder acá, este test fallaría con NotFoundError.
    fila = _fila(codigo_cliente="NO-EXISTE-999", numero_pcp="PCP-5001")

    resultado = importar_pcp_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )

    assert resultado[0]["pcp_id"] == pcp_nativo["id"]
    assert resultado[0]["accion"] == "actualizado"

    pcp_en_bd = service_client.table("pcp").select("*").eq("id", pcp_nativo["id"]).execute().data[0]
    assert pcp_en_bd["presupuesto_id"] == pcp_nativo["presupuesto_id"]
    assert pcp_en_bd["proceso_comercial_id"] == pcp_nativo["proceso_comercial_id"]


# ---------------------------------------------------------------------------
# 8.7a -- reimportar no crea un segundo proceso_comercial ni presupuesto
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reimportar_no_crea_un_segundo_proceso_comercial_ni_presupuesto(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    cliente = seed_cliente_pcp_factory(codigo_interno="CLI-6001")
    fila = _fila(codigo_cliente="CLI-6001", numero_pcp="PCP-6001")

    resultado_1 = importar_pcp_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        procesos_tras_primer_import = (
            service_client.table("procesos_comerciales")
            .select("id")
            .eq("cliente_id", cliente["id"])
            .execute()
            .data
        )
        assert len(procesos_tras_primer_import) == 1
        proceso_comercial_id = procesos_tras_primer_import[0]["id"]

        presupuestos_tras_primer_import = (
            service_client.table("presupuestos")
            .select("id")
            .eq("proceso_comercial_id", proceso_comercial_id)
            .execute()
            .data
        )
        assert len(presupuestos_tras_primer_import) == 1

        resultado_2 = importar_pcp_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )
        assert resultado_2[0]["pcp_id"] == resultado_1[0]["pcp_id"]

        procesos_tras_reimport = (
            service_client.table("procesos_comerciales")
            .select("id")
            .eq("cliente_id", cliente["id"])
            .execute()
            .data
        )
        assert len(procesos_tras_reimport) == 1
        assert procesos_tras_reimport[0]["id"] == proceso_comercial_id

        presupuestos_tras_reimport = (
            service_client.table("presupuestos")
            .select("id")
            .eq("proceso_comercial_id", proceso_comercial_id)
            .execute()
            .data
        )
        assert len(presupuestos_tras_reimport) == 1
    finally:
        pcp = service_client.table("pcp").select("*").eq("id", resultado_1[0]["pcp_id"]).execute().data[0]
        _limpiar_import(
            service_client,
            pcp_id=pcp["id"],
            presupuesto_id=pcp["presupuesto_id"],
            proceso_comercial_id=pcp["proceso_comercial_id"],
        )
