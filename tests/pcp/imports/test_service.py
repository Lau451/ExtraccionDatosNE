"""8.3-8.7a (openspec/changes/gestor-pcp/tasks.md Fase 8) + T2
(odd/tasks/presupuestos-legacy-import.md, agreed design 2026-09-24) --
pcp-legacy-import: idempotencia por `codigo_legacy`, trazabilidad vía
`pcp_legacy_map`, origen `import_legado` en los renglones, y coexistencia con
un PCP creado nativamente (spec `pcp-legacy-import`).

T2 superó el placeholder de D8 (ver docstring de
`services/pcp/imports/service.py`): el import de PCP ya NO crea
`procesos_comerciales`/`presupuestos`/`items_proceso` -- los reusa del import
legado de presupuestos (T1, `importar_presupuesto_legacy`), que estos tests
corren primero en su setup con el mismo `numero_presupuesto`/`renglon` que
después referencia el import de PCP.

RED hasta que 8.2/8.8 creen `services/pcp/imports/{repository,service}.py`.
"""

from decimal import Decimal

import pytest

from services.pcp.imports.models import FilaImportPcpLegacy, FilaImportPresupuestoLegacy
from services.pcp.imports.service import importar_pcp_legacy, importar_presupuesto_legacy
from services.shared.exceptions import NotFoundError


def _limpiar_import(service_client, *, pcp_id: str, presupuesto_id: str, proceso_comercial_id: str) -> None:
    """Orden obligatorio (RESTRICT sin CASCADE entre items_proceso/
    procesos_comerciales, docs/schema/extractor_final.sql fk_ip_proc): borrar
    `pcp` primero cascadea `pcp_renglones`/`pcp_legacy_map`/`pcp_historial`
    (fk_pcpr_pcp/fk_pcplm_pcp/fk_pcph_pcp), y `presupuestos` cascadea
    `presupuesto_items`/`presupuesto_legacy_map` -- ambos liberan la
    referencia que bloquearía el CASCADE de `items_proceso` al borrar
    `procesos_comerciales` (fk_ip_proc)."""
    service_client.table("pcp").delete().eq("id", pcp_id).execute()
    service_client.table("presupuestos").delete().eq("id", presupuesto_id).execute()
    service_client.table("procesos_comerciales").delete().eq("id", proceso_comercial_id).execute()


def _fila(
    *, codigo_cliente: str, numero_pcp: str, numero_presupuesto: str | None = None, renglon: int = 1, **overrides
) -> FilaImportPcpLegacy:
    base = {
        "codigo_cliente": codigo_cliente,
        "razon_social_cliente": "Hospital Import Test",
        "numero_pcp": numero_pcp,
        "numero_presupuesto": numero_presupuesto,
        "renglon": renglon,
        "descripcion_producto": f"Producto renglón {renglon}",
        "cantidad_producto": Decimal("10"),
        **overrides,
    }
    return FilaImportPcpLegacy(**base)


def _fila_presupuesto(
    *, codigo_cliente: str, numero_presupuesto: str, renglon: int = 1, **overrides
) -> FilaImportPresupuestoLegacy:
    base = {
        "codigo_cliente": codigo_cliente,
        "razon_social_cliente": "Hospital Import Test",
        "numero_presupuesto": numero_presupuesto,
        "renglon": renglon,
        "descripcion_producto": f"Producto renglón {renglon}",
        "cantidad_producto": Decimal("10"),
        **overrides,
    }
    return FilaImportPresupuestoLegacy(**base)


def _importar_presupuesto_previo(
    service_client,
    *,
    drogueria_id: str,
    usuario_id: str,
    codigo_cliente: str,
    numero_presupuesto: str,
    renglones: tuple[int, ...] = (1,),
) -> dict:
    """T2: el import de PCP exige un presupuesto ya importado -- helper
    compartido por estos tests para armarlo en el setup, con los mismos
    `numero_presupuesto`/`renglon` que después referencia el import de PCP."""
    filas = [
        _fila_presupuesto(codigo_cliente=codigo_cliente, numero_presupuesto=numero_presupuesto, renglon=renglon)
        for renglon in renglones
    ]
    resultado = importar_presupuesto_legacy(
        service_client, drogueria_id=drogueria_id, filas=filas, usuario_id=usuario_id
    )
    return resultado[0]


# ---------------------------------------------------------------------------
# 8.3 -- reimportar el mismo codigo_legacy actualiza el PCP existente
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reimportar_mismo_codigo_actualiza_el_pcp_existente_sin_duplicarlo(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-2001")
    _importar_presupuesto_previo(
        service_client,
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
        codigo_cliente="CLI-2001",
        numero_presupuesto="PRE-2001",
    )
    fila = _fila(codigo_cliente="CLI-2001", numero_pcp="PCP-2001", numero_presupuesto="PRE-2001")

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
    _importar_presupuesto_previo(
        service_client,
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
        codigo_cliente="CLI-2002",
        numero_presupuesto="PRE-2002",
    )
    fila = _fila(codigo_cliente="CLI-2002", numero_pcp="PCP-2002", numero_presupuesto="PRE-2002")

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
    _importar_presupuesto_previo(
        service_client,
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
        codigo_cliente="CLI-3001",
        numero_presupuesto="PRE-3001",
    )
    fila = _fila(codigo_cliente="CLI-3001", numero_pcp="PCP-3001", numero_presupuesto="PRE-3001")

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
    _importar_presupuesto_previo(
        service_client,
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
        codigo_cliente="CLI-4001",
        numero_presupuesto="PRE-4101",
    )
    fila = _fila(codigo_cliente="CLI-4001", numero_pcp="PCP-4101", numero_presupuesto="PRE-4101")

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
    # T2: el reimport busca el renglón vía items_proceso (nunca lo crea) --
    # el PCP nativo necesita al menos uno para que el renglón no se rechace.
    # Se limpia solo (CASCADE desde procesos_comerciales, liberado por la
    # propia teardown de `seed_pcp_factory`, que borra `pcp` -- y por lo
    # tanto `pcp_renglones` -- antes que `presupuestos`).
    item = (
        service_client.table("items_proceso")
        .insert(
            {
                "proceso_comercial_id": pcp_nativo["proceso_comercial_id"],
                "drogueria_id": seed_drogueria["id"],
                "numero_renglon": 1,
                "descripcion": "Renglón nativo de test",
                "cantidad": "10",
            }
        )
        .execute()
        .data[0]
    )
    service_client.table("pcp_legacy_map").insert(
        {"pcp_id": pcp_nativo["id"], "drogueria_id": seed_drogueria["id"], "codigo_legacy": "PCP-5001"}
    ).execute()

    # codigo_cliente deliberadamente irresoluble y numero_presupuesto ausente:
    # en la rama de reimport nunca se llega a `_resolver_cliente_id` ni a la
    # resolución del presupuesto (T2, "procesos_comerciales/presupuestos
    # NUNCA se tocan de nuevo") -- si el import intentara resolver cualquiera
    # de los dos de nuevo, este test fallaría con NotFoundError.
    fila = _fila(codigo_cliente="NO-EXISTE-999", numero_pcp="PCP-5001", numero_presupuesto=None)

    resultado = importar_pcp_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )

    assert resultado[0]["pcp_id"] == pcp_nativo["id"]
    assert resultado[0]["accion"] == "actualizado"

    pcp_en_bd = service_client.table("pcp").select("*").eq("id", pcp_nativo["id"]).execute().data[0]
    assert pcp_en_bd["presupuesto_id"] == pcp_nativo["presupuesto_id"]
    assert pcp_en_bd["proceso_comercial_id"] == pcp_nativo["proceso_comercial_id"]

    renglones = (
        service_client.table("pcp_renglones")
        .select("item_proceso_id")
        .eq("pcp_id", pcp_nativo["id"])
        .execute()
        .data
    )
    assert len(renglones) == 1
    assert renglones[0]["item_proceso_id"] == item["id"]


# ---------------------------------------------------------------------------
# 8.7a -- reimportar no crea un segundo proceso_comercial ni presupuesto
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reimportar_no_crea_un_segundo_proceso_comercial_ni_presupuesto(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    cliente = seed_cliente_pcp_factory(codigo_interno="CLI-6001")
    presupuesto = _importar_presupuesto_previo(
        service_client,
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
        codigo_cliente="CLI-6001",
        numero_presupuesto="PRE-6001",
    )
    proceso_comercial_id = (
        service_client.table("presupuestos")
        .select("proceso_comercial_id")
        .eq("id", presupuesto["presupuesto_id"])
        .execute()
        .data[0]["proceso_comercial_id"]
    )
    fila = _fila(codigo_cliente="CLI-6001", numero_pcp="PCP-6001", numero_presupuesto="PRE-6001")

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
        assert procesos_tras_primer_import[0]["id"] == proceso_comercial_id

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


# ---------------------------------------------------------------------------
# T2 -- sin numero_presupuesto: se rechaza sin crear nada
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_pcp_sin_numero_presupuesto_es_rechazado(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-7002")
    fila = _fila(codigo_cliente="CLI-7002", numero_pcp="PCP-7002", numero_presupuesto=None)

    with pytest.raises(NotFoundError):
        importar_pcp_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )

    mapa = (
        service_client.table("pcp_legacy_map")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", "PCP-7002")
        .execute()
        .data
    )
    assert mapa == []


# ---------------------------------------------------------------------------
# T2 -- numero_presupuesto no importado todavía: se rechaza ("importalo
# primero"), sin crear nada
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_pcp_sin_presupuesto_importado_es_rechazado(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-7001")
    fila = _fila(codigo_cliente="CLI-7001", numero_pcp="PCP-7001", numero_presupuesto="PRE-NO-EXISTE-7001")

    with pytest.raises(NotFoundError):
        importar_pcp_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )

    mapa = (
        service_client.table("pcp_legacy_map")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", "PCP-7001")
        .execute()
        .data
    )
    assert mapa == []


# ---------------------------------------------------------------------------
# T2 -- el renglón pedido no existe en el presupuesto ya importado: se
# rechaza en vez de crearlo
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_pcp_renglon_no_existe_en_el_presupuesto_es_rechazado(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-7003")
    presupuesto = _importar_presupuesto_previo(
        service_client,
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
        codigo_cliente="CLI-7003",
        numero_presupuesto="PRE-7003",
        renglones=(1,),
    )
    # el presupuesto solo tiene el renglón 1 -- el PCP pide el 1 (válido) y el
    # 2, que no existe. El lote se valida entero ANTES de escribir: el
    # rechazo no puede dejar un `pcp`/`pcp_legacy_map` a medio crear.
    filas = [
        _fila(codigo_cliente="CLI-7003", numero_pcp="PCP-7003", numero_presupuesto="PRE-7003", renglon=1),
        _fila(codigo_cliente="CLI-7003", numero_pcp="PCP-7003", numero_presupuesto="PRE-7003", renglon=2),
    ]

    try:
        with pytest.raises(NotFoundError, match="renglón 2 del PCP PCP-7003 no existe"):
            importar_pcp_legacy(
                service_client,
                drogueria_id=seed_drogueria["id"],
                filas=filas,
                usuario_id=seed_usuario_sistema["id"],
            )
        mapa_tras_rechazo = (
            service_client.table("pcp_legacy_map")
            .select("pcp_id")
            .eq("drogueria_id", seed_drogueria["id"])
            .eq("codigo_legacy", "PCP-7003")
            .execute()
            .data
        )
        assert mapa_tras_rechazo == []
    finally:
        mapa = (
            service_client.table("pcp_legacy_map")
            .select("pcp_id")
            .eq("drogueria_id", seed_drogueria["id"])
            .eq("codigo_legacy", "PCP-7003")
            .execute()
            .data
        )
        if mapa:
            service_client.table("pcp").delete().eq("id", mapa[0]["pcp_id"]).execute()
        proceso_comercial_id = (
            service_client.table("presupuestos")
            .select("proceso_comercial_id")
            .eq("id", presupuesto["presupuesto_id"])
            .execute()
            .data[0]["proceso_comercial_id"]
        )
        service_client.table("presupuestos").delete().eq("id", presupuesto["presupuesto_id"]).execute()
        service_client.table("procesos_comerciales").delete().eq("id", proceso_comercial_id).execute()


# ---------------------------------------------------------------------------
# T2 -- happy path: el PCP reusa el proceso_comercial/presupuesto/items_proceso
# del presupuesto ya importado, sin crear ningún items_proceso nuevo
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_pcp_reusa_el_proceso_y_los_items_del_presupuesto_importado(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-7004")
    presupuesto = _importar_presupuesto_previo(
        service_client,
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
        codigo_cliente="CLI-7004",
        numero_presupuesto="PRE-7004",
        renglones=(1, 2),
    )
    proceso_comercial_id = (
        service_client.table("presupuestos")
        .select("proceso_comercial_id")
        .eq("id", presupuesto["presupuesto_id"])
        .execute()
        .data[0]["proceso_comercial_id"]
    )
    items_antes = (
        service_client.table("items_proceso")
        .select("id")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .execute()
        .data
    )
    assert len(items_antes) == 2

    fila = _fila(codigo_cliente="CLI-7004", numero_pcp="PCP-7004", numero_presupuesto="PRE-7004", renglon=1)

    resultado = importar_pcp_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        assert resultado[0]["accion"] == "creado"
        pcp = service_client.table("pcp").select("*").eq("id", resultado[0]["pcp_id"]).execute().data[0]
        assert pcp["presupuesto_id"] == presupuesto["presupuesto_id"]
        assert pcp["proceso_comercial_id"] == proceso_comercial_id

        items_despues = (
            service_client.table("items_proceso")
            .select("id")
            .eq("proceso_comercial_id", proceso_comercial_id)
            .execute()
            .data
        )
        assert len(items_despues) == 2  # ningún items_proceso nuevo

        ids_items_antes = {item["id"] for item in items_antes}
        renglon = (
            service_client.table("pcp_renglones")
            .select("item_proceso_id")
            .eq("pcp_id", resultado[0]["pcp_id"])
            .execute()
            .data[0]
        )
        assert renglon["item_proceso_id"] in ids_items_antes
    finally:
        _limpiar_import(
            service_client,
            pcp_id=resultado[0]["pcp_id"],
            presupuesto_id=presupuesto["presupuesto_id"],
            proceso_comercial_id=proceso_comercial_id,
        )
