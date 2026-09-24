"""Import legado de presupuestos (engram #647, agreed design 2026-09-24,
odd/tasks/presupuestos-legacy-import.md T1) -- idempotencia por
`numero_presupuesto` vía `presupuesto_legacy_map` (migración 0015),
resolución de `producto_id` por `codigo_producto`, y compensación manual
ante una falla a mitad de camino (mismo criterio que
`services/presupuestacion/extraccion/service.py::_materializar_orden_compra`).

RED hasta que `services/pcp/imports/{repository,service}.py` expongan
`importar_presupuesto_legacy`.
"""

from decimal import Decimal

import pytest
from postgrest.exceptions import APIError

from services.pcp.imports import repository as repo
from services.pcp.imports.models import FilaImportPresupuestoLegacy
from services.pcp.imports.service import importar_presupuesto_legacy
from services.shared.exceptions import NotFoundError


def _limpiar_import(service_client, *, presupuesto_id: str, proceso_comercial_id: str) -> None:
    """Orden obligatorio (RESTRICT sin CASCADE entre items_proceso/
    procesos_comerciales, docs/schema/extractor_final.sql fk_ip_proc): borrar
    `presupuestos` primero cascadea `presupuesto_items` (fk_pi_pre) y
    `presupuesto_legacy_map` (fk_prelm_presupuesto), liberando la referencia
    que bloquearía el CASCADE de `items_proceso` al borrar
    `procesos_comerciales` (fk_ip_proc) -- mismo criterio que
    tests/pcp/imports/test_service.py::_limpiar_import."""
    service_client.table("presupuestos").delete().eq("id", presupuesto_id).execute()
    service_client.table("procesos_comerciales").delete().eq("id", proceso_comercial_id).execute()


def _fila(*, codigo_cliente: str, numero_presupuesto: str, renglon: int = 1, **overrides) -> FilaImportPresupuestoLegacy:
    base = {
        "codigo_cliente": codigo_cliente,
        "razon_social_cliente": "Hospital Presupuesto Test",
        "numero_presupuesto": numero_presupuesto,
        "renglon": renglon,
        "descripcion_producto": f"Producto renglón {renglon}",
        "cantidad_producto": Decimal("10"),
        **overrides,
    }
    return FilaImportPresupuestoLegacy(**base)


# ---------------------------------------------------------------------------
# Primer import: crea proceso_comercial + presupuesto + map + items_proceso +
# presupuesto_items
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_primer_import_crea_proceso_presupuesto_map_e_items(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-1001")
    fila = _fila(
        codigo_cliente="CLI-PRE-1001",
        numero_presupuesto="PRE-1001",
        proceso_comercial="2",
        importe_total=Decimal("500.50"),
        precio_producto=Decimal("50.05"),
    )

    resultado = importar_presupuesto_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    proceso_comercial_id = (
        service_client.table("presupuestos")
        .select("proceso_comercial_id")
        .eq("id", resultado[0]["presupuesto_id"])
        .execute()
        .data[0]["proceso_comercial_id"]
    )
    try:
        assert resultado[0]["accion"] == "creado"
        assert resultado[0]["codigo_legacy"] == "PRE-1001"
        assert resultado[0]["renglones_procesados"] == 1
        assert resultado[0]["renglones_sin_producto"] == 1  # codigo_producto no vino

        presupuesto = (
            service_client.table("presupuestos")
            .select("*")
            .eq("id", resultado[0]["presupuesto_id"])
            .execute()
            .data[0]
        )
        assert presupuesto["estado"] == "generado"
        assert Decimal(str(presupuesto["monto_total"])) == Decimal("500.50")
        assert presupuesto["cantidad_items"] == 1
        assert presupuesto["items_sin_precio"] == 0  # precio_producto SÍ vino

        proceso = (
            service_client.table("procesos_comerciales")
            .select("clase")
            .eq("id", presupuesto["proceso_comercial_id"])
            .execute()
            .data[0]
        )
        assert proceso["clase"] == "licitacion"  # proceso_comercial "2" -> licitacion

        mapa = (
            service_client.table("presupuesto_legacy_map")
            .select("presupuesto_id, datos_legacy")
            .eq("drogueria_id", seed_drogueria["id"])
            .eq("codigo_legacy", "PRE-1001")
            .execute()
            .data
        )
        assert len(mapa) == 1
        assert mapa[0]["presupuesto_id"] == resultado[0]["presupuesto_id"]
        assert isinstance(mapa[0]["datos_legacy"], list)  # filas crudas del grupo, no solo la cabecera
        assert len(mapa[0]["datos_legacy"]) == 1

        items = (
            service_client.table("items_proceso")
            .select("numero_renglon, descripcion, cantidad, producto_id")
            .eq("proceso_comercial_id", presupuesto["proceso_comercial_id"])
            .execute()
            .data
        )
        assert len(items) == 1
        assert items[0]["numero_renglon"] == 1
        assert items[0]["producto_id"] is None

        presupuesto_items = (
            service_client.table("presupuesto_items")
            .select("precio_unitario, cantidad_ofertada, metodo_precio, producto_id")
            .eq("presupuesto_id", resultado[0]["presupuesto_id"])
            .execute()
            .data
        )
        assert len(presupuesto_items) == 1
        assert Decimal(str(presupuesto_items[0]["precio_unitario"])) == Decimal("50.05")
        assert Decimal(str(presupuesto_items[0]["cantidad_ofertada"])) == Decimal("10")
        assert presupuesto_items[0]["metodo_precio"] == "manual"
    finally:
        _limpiar_import(
            service_client,
            presupuesto_id=resultado[0]["presupuesto_id"],
            proceso_comercial_id=proceso_comercial_id,
        )


# ---------------------------------------------------------------------------
# Reimportar el mismo numero_presupuesto: no duplica nada, accion='existente'
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reimportar_mismo_numero_no_duplica_nada_y_retorna_existente(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-2001")
    fila = _fila(codigo_cliente="CLI-PRE-2001", numero_presupuesto="PRE-2001")

    resultado_1 = importar_presupuesto_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        proceso_comercial_id = (
            service_client.table("presupuestos")
            .select("proceso_comercial_id")
            .eq("id", resultado_1[0]["presupuesto_id"])
            .execute()
            .data[0]["proceso_comercial_id"]
        )

        resultado_2 = importar_presupuesto_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )

        assert resultado_2[0]["accion"] == "existente"
        assert resultado_2[0]["presupuesto_id"] == resultado_1[0]["presupuesto_id"]

        mapa = (
            service_client.table("presupuesto_legacy_map")
            .select("id")
            .eq("drogueria_id", seed_drogueria["id"])
            .eq("codigo_legacy", "PRE-2001")
            .execute()
            .data
        )
        assert len(mapa) == 1

        presupuesto_items = (
            service_client.table("presupuesto_items")
            .select("id")
            .eq("presupuesto_id", resultado_1[0]["presupuesto_id"])
            .execute()
            .data
        )
        assert len(presupuesto_items) == 1

        items_proceso = (
            service_client.table("items_proceso")
            .select("id")
            .eq("proceso_comercial_id", proceso_comercial_id)
            .execute()
            .data
        )
        assert len(items_proceso) == 1

        procesos = (
            service_client.table("procesos_comerciales")
            .select("id")
            .eq("id", proceso_comercial_id)
            .execute()
            .data
        )
        assert len(procesos) == 1
    finally:
        _limpiar_import(
            service_client,
            presupuesto_id=resultado_1[0]["presupuesto_id"],
            proceso_comercial_id=proceso_comercial_id,
        )


# ---------------------------------------------------------------------------
# T1b(a): reimport debe reportar el mismo renglones_sin_producto que el
# primer import -- antes leía presupuestos.items_sin_precio (métrica
# distinta: renglones sin PRECIO, no sin producto_id resuelto). Fila con
# precio (items_sin_precio=0) pero sin codigo_producto (producto_id NULL)
# separa ambas métricas, que antes coincidían por casualidad en los tests
# sin precio_producto.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reimportar_reporta_el_mismo_renglones_sin_producto_que_el_primer_import(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-9001")
    fila = _fila(
        codigo_cliente="CLI-PRE-9001", numero_presupuesto="PRE-9001", precio_producto=Decimal("5.00")
    )

    resultado_1 = importar_presupuesto_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    proceso_comercial_id = (
        service_client.table("presupuestos")
        .select("proceso_comercial_id")
        .eq("id", resultado_1[0]["presupuesto_id"])
        .execute()
        .data[0]["proceso_comercial_id"]
    )
    try:
        assert resultado_1[0]["renglones_sin_producto"] == 1  # sin codigo_producto -> no resuelto

        resultado_2 = importar_presupuesto_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )
        assert resultado_2[0]["accion"] == "existente"
        assert resultado_2[0]["renglones_sin_producto"] == resultado_1[0]["renglones_sin_producto"]
    finally:
        _limpiar_import(
            service_client,
            presupuesto_id=resultado_1[0]["presupuesto_id"],
            proceso_comercial_id=proceso_comercial_id,
        )


# ---------------------------------------------------------------------------
# producto_id: resuelto cuando codigo_producto matchea productos.codigo_interno
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_producto_id_resuelto_desde_codigo_producto(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory, seed_producto_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-3001")
    producto = seed_producto_factory()
    fila = _fila(
        codigo_cliente="CLI-PRE-3001",
        numero_presupuesto="PRE-3001",
        codigo_producto=producto["codigo_interno"],
        precio_producto=Decimal("12.34"),
    )

    resultado = importar_presupuesto_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        assert resultado[0]["renglones_sin_producto"] == 0

        proceso_comercial_id = (
            service_client.table("presupuestos")
            .select("proceso_comercial_id")
            .eq("id", resultado[0]["presupuesto_id"])
            .execute()
            .data[0]["proceso_comercial_id"]
        )
        item = (
            service_client.table("items_proceso")
            .select("producto_id")
            .eq("proceso_comercial_id", proceso_comercial_id)
            .execute()
            .data[0]
        )
        assert item["producto_id"] == producto["id"]

        presupuesto_item = (
            service_client.table("presupuesto_items")
            .select("producto_id")
            .eq("presupuesto_id", resultado[0]["presupuesto_id"])
            .execute()
            .data[0]
        )
        assert presupuesto_item["producto_id"] == producto["id"]
    finally:
        _limpiar_import(
            service_client,
            presupuesto_id=resultado[0]["presupuesto_id"],
            proceso_comercial_id=proceso_comercial_id,
        )


# ---------------------------------------------------------------------------
# codigo_producto ausente o desconocido -> producto_id NULL, la fila no falla
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_codigo_producto_desconocido_no_falla_la_fila(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-4001")
    fila = _fila(
        codigo_cliente="CLI-PRE-4001", numero_presupuesto="PRE-4001", codigo_producto="NO-EXISTE-CODIGO"
    )

    resultado = importar_presupuesto_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
    )
    try:
        assert resultado[0]["renglones_sin_producto"] == 1
        proceso_comercial_id = (
            service_client.table("presupuestos")
            .select("proceso_comercial_id")
            .eq("id", resultado[0]["presupuesto_id"])
            .execute()
            .data[0]["proceso_comercial_id"]
        )
    finally:
        _limpiar_import(
            service_client,
            presupuesto_id=resultado[0]["presupuesto_id"],
            proceso_comercial_id=proceso_comercial_id,
        )


# ---------------------------------------------------------------------------
# Cliente desconocido: NotFoundError, sin crear ningún placeholder
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cliente_desconocido_lanza_notfound_sin_crear_nada(
    service_client, seed_drogueria, seed_usuario_sistema
):
    fila = _fila(codigo_cliente="NO-EXISTE-CLI-999", numero_presupuesto="PRE-5001")

    with pytest.raises(NotFoundError):
        importar_presupuesto_legacy(
            service_client, drogueria_id=seed_drogueria["id"], filas=[fila], usuario_id=seed_usuario_sistema["id"]
        )

    mapa = (
        service_client.table("presupuesto_legacy_map")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", "PRE-5001")
        .execute()
        .data
    )
    assert mapa == []


# ---------------------------------------------------------------------------
# Falla a mitad de camino (numero_renglon duplicado -> unique_violation en
# items_proceso): compensa borrando presupuesto+proceso+items_proceso, sin
# dejar huérfanos que bloqueen un reintento (T1b(b): excepción específica,
# no `Exception` a secas, y verificación explícita de las tres entidades).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_falla_a_mitad_de_camino_compensa_y_permite_reintentar(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory, monkeypatch
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-6001")
    filas_invalidas = [
        _fila(codigo_cliente="CLI-PRE-6001", numero_presupuesto="PRE-6001", renglon=1),
        _fila(codigo_cliente="CLI-PRE-6001", numero_presupuesto="PRE-6001", renglon=1),  # renglón duplicado
    ]

    # Espía sobre los creadores para capturar los ids ANTES de que la
    # compensación los borre -- necesarios para verificar directamente que
    # presupuesto/proceso_comercial/items_proceso quedaron gone, no solo
    # inferirlo de forma indirecta.
    ids_creados: dict[str, str] = {}
    proceso_original = repo.crear_proceso_comercial
    presupuesto_original = repo.crear_presupuesto
    item_original = repo.crear_item_proceso

    def _proceso_spy(client, fila):
        resultado = proceso_original(client, fila)
        ids_creados["proceso_comercial_id"] = resultado["id"]
        return resultado

    def _presupuesto_spy(client, fila):
        resultado = presupuesto_original(client, fila)
        ids_creados["presupuesto_id"] = resultado["id"]
        return resultado

    def _item_spy(client, fila):
        resultado = item_original(client, fila)
        ids_creados.setdefault("items_proceso_ids", []).append(resultado["id"])
        return resultado

    monkeypatch.setattr(repo, "crear_proceso_comercial", _proceso_spy)
    monkeypatch.setattr(repo, "crear_presupuesto", _presupuesto_spy)
    monkeypatch.setattr(repo, "crear_item_proceso", _item_spy)

    with pytest.raises(APIError) as exc_info:
        importar_presupuesto_legacy(
            service_client,
            drogueria_id=seed_drogueria["id"],
            filas=filas_invalidas,
            usuario_id=seed_usuario_sistema["id"],
        )
    assert exc_info.value.code == "23505"  # unique_violation (uq_items_proceso)

    proceso_comercial_id = ids_creados["proceso_comercial_id"]
    presupuesto_id = ids_creados["presupuesto_id"]
    items_proceso_ids = ids_creados.get("items_proceso_ids", [])
    assert items_proceso_ids  # el primer renglón sí llegó a crear su items_proceso

    mapa = (
        service_client.table("presupuesto_legacy_map")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", "PRE-6001")
        .execute()
        .data
    )
    assert mapa == []  # sin huérfano: el map se compensó junto con presupuesto/proceso

    presupuestos = (
        service_client.table("presupuestos").select("id").eq("id", presupuesto_id).execute().data
    )
    assert presupuestos == []  # presupuesto compensado

    procesos = (
        service_client.table("procesos_comerciales")
        .select("id")
        .eq("id", proceso_comercial_id)
        .execute()
        .data
    )
    assert procesos == []  # proceso_comercial compensado

    items_proceso = (
        service_client.table("items_proceso")
        .select("id")
        .in_("id", items_proceso_ids)
        .execute()
        .data
    )
    assert items_proceso == []  # items_proceso del renglón ya creado también compensado (cascade del proceso)

    # reintento con datos válidos: debe poder crear todo limpio, sin conflicto
    fila_valida = _fila(codigo_cliente="CLI-PRE-6001", numero_presupuesto="PRE-6001", renglon=1)
    resultado = importar_presupuesto_legacy(
        service_client,
        drogueria_id=seed_drogueria["id"],
        filas=[fila_valida],
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        assert resultado[0]["accion"] == "creado"
        proceso_comercial_id = (
            service_client.table("presupuestos")
            .select("proceso_comercial_id")
            .eq("id", resultado[0]["presupuesto_id"])
            .execute()
            .data[0]["proceso_comercial_id"]
        )
    finally:
        _limpiar_import(
            service_client,
            presupuesto_id=resultado[0]["presupuesto_id"],
            proceso_comercial_id=proceso_comercial_id,
        )


# ---------------------------------------------------------------------------
# T1b(d): si `borrar_presupuesto` (primer paso de la compensación) también
# falla, el error ORIGINAL (el que disparó la compensación) debe seguir
# siendo el que se propaga -- no el de la compensación -- y
# `borrar_proceso_comercial` (segundo paso) debe correr igual.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_compensacion_re_lanza_el_error_original_y_borra_proceso_aunque_falle_borrar_presupuesto(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory, monkeypatch
):
    cliente = seed_cliente_pcp_factory(codigo_interno="CLI-PRE-6501")
    filas_invalidas = [
        _fila(codigo_cliente="CLI-PRE-6501", numero_presupuesto="PRE-6501", renglon=1),
        _fila(codigo_cliente="CLI-PRE-6501", numero_presupuesto="PRE-6501", renglon=1),  # renglón duplicado
    ]

    borrar_presupuesto_original = repo.borrar_presupuesto

    def _borrar_presupuesto_que_falla(client, *, presupuesto_id):
        # Corre el borrado real (para no dejar un huérfano que confunda la
        # aserción de `procesos_comerciales` de abajo) pero simula que la
        # propia compensación también falló -- el punto del test es que ESE
        # error nunca debe pisar al original (unique_violation).
        borrar_presupuesto_original(client, presupuesto_id=presupuesto_id)
        raise RuntimeError("fallo simulado al borrar presupuesto durante la compensación")

    monkeypatch.setattr(repo, "borrar_presupuesto", _borrar_presupuesto_que_falla)

    with pytest.raises(APIError) as exc_info:
        importar_presupuesto_legacy(
            service_client,
            drogueria_id=seed_drogueria["id"],
            filas=filas_invalidas,
            usuario_id=seed_usuario_sistema["id"],
        )
    assert exc_info.value.code == "23505"  # el original, no el RuntimeError simulado

    procesos = (
        service_client.table("procesos_comerciales")
        .select("id")
        .eq("cliente_id", cliente["id"])
        .execute()
        .data
    )
    assert procesos == []  # borrar_proceso_comercial corrió pese al fallo simulado de borrar_presupuesto


# ---------------------------------------------------------------------------
# T1b(e): un lote con 2+ numero_presupuesto distintos agrupa correctamente y
# devuelve un resultado por cada uno, en el mismo orden en que aparecieron
# (OrderedDict, mismo criterio que importar_pcp_legacy).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_lote_con_multiples_numero_presupuesto_agrupa_y_devuelve_un_resultado_por_cada_uno_en_orden(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_pcp_factory
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-8001")
    filas = [
        _fila(codigo_cliente="CLI-PRE-8001", numero_presupuesto="PRE-8001", renglon=1),
        _fila(codigo_cliente="CLI-PRE-8001", numero_presupuesto="PRE-8002", renglon=1),
        _fila(codigo_cliente="CLI-PRE-8001", numero_presupuesto="PRE-8001", renglon=2),
    ]

    resultado = importar_presupuesto_legacy(
        service_client, drogueria_id=seed_drogueria["id"], filas=filas, usuario_id=seed_usuario_sistema["id"]
    )
    try:
        assert [r["codigo_legacy"] for r in resultado] == ["PRE-8001", "PRE-8002"]
        assert resultado[0]["accion"] == "creado"
        assert resultado[1]["accion"] == "creado"
        assert resultado[0]["renglones_procesados"] == 2  # PRE-8001: renglones 1 y 2
        assert resultado[1]["renglones_procesados"] == 1  # PRE-8002: solo renglón 1
        assert resultado[0]["presupuesto_id"] != resultado[1]["presupuesto_id"]
    finally:
        for fila_resultado in resultado:
            proceso_comercial_id = (
                service_client.table("presupuestos")
                .select("proceso_comercial_id")
                .eq("id", fila_resultado["presupuesto_id"])
                .execute()
                .data[0]["proceso_comercial_id"]
            )
            _limpiar_import(
                service_client,
                presupuesto_id=fila_resultado["presupuesto_id"],
                proceso_comercial_id=proceso_comercial_id,
            )
