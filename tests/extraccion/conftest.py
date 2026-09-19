import csv as csv_module
import secrets
import uuid

import pytest

from services.presupuestacion.core.texto import normalizar_descripcion


def _borrar_orden_compra_en_cascada(service_client, *, orden_compra_id: str) -> None:
    """Orden de borrado manual para una fila de `ordenes_compra` creada por
    Phase 5 (`_materializar_orden_compra`) -- mismo patrón que
    `tests/compras/conftest.py::limpiar_ordenes_compra`. `entregas_oc_items.
    oc_item_id` (fk_eoci_oci) NO tiene ON DELETE CASCADE, así que un DELETE
    directo sobre `ordenes_compra` revienta con FK violation si no se borra
    esto a mano primero: `ordenes_compra`.CASCADE -> `oc_items`/`entregas_oc`
    en paralelo, pero `entregas_oc_items` solo cascadea desde `entregas_oc`
    (no desde `oc_items`), y Postgres puede intentar borrar `oc_items` antes
    de que la cascada de `entregas_oc` haya limpiado `entregas_oc_items`."""
    entregas = (
        service_client.table("entregas_oc")
        .select("id")
        .eq("orden_compra_id", orden_compra_id)
        .execute()
        .data
    )
    for entrega in entregas:
        service_client.table("entregas_oc_items").delete().eq(
            "entrega_oc_id", entrega["id"]
        ).execute()
    for entrega in entregas:
        service_client.table("entregas_oc").delete().eq("id", entrega["id"]).execute()

    service_client.table("historial_cambios").delete().eq(
        "orden_compra_id", orden_compra_id
    ).execute()
    service_client.table("oc_items").delete().eq("orden_compra_id", orden_compra_id).execute()
    service_client.table("ordenes_compra").delete().eq("id", orden_compra_id).execute()


@pytest.fixture
def seed_cliente_factory(service_client, seed_drogueria):
    """Alta de cliente en dos pasos (terceros + clientes), mismo patrón que
    tests/conftest.py::seed_proveedor -- `clientes` comparte `id` con `terceros`
    desde 0008_terceros_modelo.sql y no tiene columnas de identidad propias
    (razon_social/cuit/codigo_interno viven en terceros). Devuelve un dict
    combinado con los campos que resolver_cliente_candidato necesita armar en
    CandidatoCliente, para que los tests de integración no tengan que volver a
    unir las dos tablas a mano."""
    creados: list[tuple[str, str]] = []  # (tercero_id, drogueria_id) para el teardown

    def _seed(
        razon_social: str = "Cliente de test",
        *,
        drogueria_id: str | None = None,
        cuit: str | None = None,
        cuit_no_exclusivo: bool = False,
        codigo_interno: str | None = None,
        tipo: str = "hospital",
        activo: bool = True,
    ) -> dict:
        drog_id = drogueria_id or seed_drogueria["id"]
        tercero = (
            service_client.table("terceros")
            .insert(
                {
                    "drogueria_id": drog_id,
                    "razon_social": razon_social,
                    "cuit": cuit,
                    "cuit_no_exclusivo": cuit_no_exclusivo,
                    "codigo_interno": codigo_interno,
                }
            )
            .execute()
            .data[0]
        )
        cliente = (
            service_client.table("clientes")
            .insert({"id": tercero["id"], "drogueria_id": drog_id, "tipo": tipo, "activo": activo})
            .execute()
            .data[0]
        )
        creados.append((tercero["id"], drog_id))
        return {
            "cliente_id": cliente["id"],
            "drogueria_id": drog_id,
            "razon_social": tercero["razon_social"],
            "cuit": tercero["cuit"],
            "cuit_no_exclusivo": tercero["cuit_no_exclusivo"],
            "codigo_interno": tercero["codigo_interno"],
            "tipo": cliente["tipo"],
            "activo": cliente["activo"],
        }

    yield _seed
    for tercero_id, _drog_id in creados:
        # 0025 (Phase 5): ordenes_compra.cliente_id (fk_oc_cli) y
        # oc_cliente_alias.cliente_id (fk_oca_cliente) NO tienen ON DELETE
        # CASCADE -- si un test de integración confirmó una OC contra este
        # cliente o le aprendió un alias (_registrar_alias_cliente), hay que
        # limpiar eso ANTES de borrar el tercero. El orden de teardown entre
        # fixtures independientes (esta y seed_extraction_result_factory) NO
        # está garantizado, así que este cleanup es redundante a propósito:
        # si ya se borró desde el otro lado, estas queries no encuentran nada.
        ordenes = (
            service_client.table("ordenes_compra")
            .select("id")
            .eq("cliente_id", tercero_id)
            .execute()
            .data
        )
        for oc in ordenes:
            _borrar_orden_compra_en_cascada(service_client, orden_compra_id=oc["id"])
        service_client.table("oc_cliente_alias").delete().eq("cliente_id", tercero_id).execute()
        # fk_cli_tercero (clientes -> terceros) es ON DELETE CASCADE -- borrar el
        # tercero alcanza para limpiar la fila de rol también.
        service_client.table("terceros").delete().eq("id", tercero_id).execute()


@pytest.fixture
def seed_alias_cliente_factory(service_client, seed_drogueria):
    """Alta directa de una fila de `oc_cliente_alias` para tests de integración
    del nivel 1 (D3.1) -- no pasa por upsert_alias_cliente a propósito, para
    poder armar el estado inicial exacto que cada test necesita."""
    creados: list[str] = []

    def _seed(*, cliente_id: str, texto_original: str, drogueria_id: str | None = None, **overrides):
        fila = {
            "drogueria_id": drogueria_id or seed_drogueria["id"],
            "texto_extraido_normalizado": normalizar_descripcion(texto_original),
            "texto_extraido_original": texto_original,
            "cliente_id": cliente_id,
            **overrides,
        }
        alias = service_client.table("oc_cliente_alias").insert(fila).execute().data[0]
        creados.append(alias["id"])
        return alias

    yield _seed
    for alias_id in creados:
        service_client.table("oc_cliente_alias").delete().eq("id", alias_id).execute()


@pytest.fixture
def seed_proceso_con_cliente(service_client, seed_drogueria):
    fila = {
        "drogueria_id": seed_drogueria["id"],
        "nombre": "Hospital de test",
        "tipo": "hospital",
    }
    cliente = service_client.table("clientes").insert(fila).execute().data[0]

    fila_proceso = {
        "drogueria_id": seed_drogueria["id"],
        "cliente_id": cliente["id"],
        "clase": "cotizacion",
        "nombre": "Proceso de test con cliente",
    }
    proceso = service_client.table("procesos_comerciales").insert(fila_proceso).execute().data[0]

    yield proceso

    service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()
    service_client.table("clientes").delete().eq("id", cliente["id"]).execute()


@pytest.fixture
def seed_extraction_result_factory(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema, tmp_path
):
    # Depende explícitamente de seed_proceso_comercial y seed_usuario_sistema (aunque no
    # los use en el setup) para garantizar que las filas creadas acá -- que referencian a
    # ambos vía extraction_results.proceso_comercial_id/validado_por -- se borren ANTES
    # que ellos. Mismo motivo que en matching/presupuestos: el orden de teardown de
    # pytest sigue el grafo de dependencias, no el orden de aparición en la firma del test.
    creados: list[dict] = []

    def _seed(document_type: str, filas: list[dict], columnas: list[str], **overrides):
        csv_path = tmp_path / f"extraccion-{uuid.uuid4().hex[:8]}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_module.DictWriter(f, fieldnames=columnas, delimiter=";")
            writer.writeheader()
            writer.writerows(filas)

        fila = {
            "drogueria_id": seed_drogueria["id"],
            "document_type": document_type,
            "source_filename": "test.pdf",
            "source_sha256": secrets.token_hex(32),
            "row_count": len(filas),
            "csv_disk_path": str(csv_path),
            "status": "completed",
            **overrides,
        }
        extraction = service_client.table("extraction_results").insert(fila).execute().data[0]
        creados.append(extraction)
        return extraction

    yield _seed

    # comparativas.reemplaza_id se auto-referencia (versión nueva -> vieja) y puede
    # cruzar extracciones distintas (extraction_1 crea la vieja, extraction_2 crea la
    # nueva que la referencia). Hay que romper TODAS las auto-referencias en una pasada
    # separada, antes de borrar nada — si no, procesar extraction_1 primero intenta
    # borrar la comparativa vieja mientras la de extraction_2 todavía la referencia.
    comparativas_por_extraccion: dict[str, list[dict]] = {}
    for extraction in creados:
        comparativas_por_extraccion[extraction["id"]] = (
            service_client.table("comparativas")
            .select("id")
            .eq("extraction_id", extraction["id"])
            .execute()
            .data
        )
    for comparativas in comparativas_por_extraccion.values():
        for comparativa in comparativas:
            # ck_comp_motivo exige que reemplaza_id y motivo_version sean NULL juntos o
            # no-NULL juntos -- hay que limpiar los dos, no solo reemplaza_id.
            service_client.table("comparativas").update(
                {"reemplaza_id": None, "motivo_version": None}
            ).eq("id", comparativa["id"]).execute()

    for extraction in creados:
        extraction_id = extraction["id"]
        comparativas = comparativas_por_extraccion[extraction_id]

        for comparativa in comparativas:
            # notificacion_entregas.notificacion_id (fk_ne_notif) SÍ tiene ON DELETE
            # CASCADE, pero se borra explícito igual: el fix de D6 (5.2) hace que cada
            # reemplazo de comparativa cree filas acá, y depender solo del cascade deja
            # el orden de limpieza implícito en vez de documentado.
            notificaciones = (
                service_client.table("notificaciones")
                .select("id")
                .eq("comparativa_id", comparativa["id"])
                .execute()
                .data
            )
            for notificacion in notificaciones:
                service_client.table("notificacion_entregas").delete().eq(
                    "notificacion_id", notificacion["id"]
                ).execute()
            service_client.table("notificaciones").delete().eq(
                "comparativa_id", comparativa["id"]
            ).execute()
            service_client.table("ofertas_items").delete().eq(
                "comparativa_id", comparativa["id"]
            ).execute()
            # historial_cambios.comparativa_id (fk_hc_comp) no tiene CASCADE -- hay que
            # borrar el historial antes que la comparativa que referencia, ahora que crear
            # y reemplazar una comparativa generan filas de auditoría.
            service_client.table("historial_cambios").delete().eq(
                "comparativa_id", comparativa["id"]
            ).execute()
        for comparativa in comparativas:
            service_client.table("comparativas").delete().eq("id", comparativa["id"]).execute()

        items = (
            service_client.table("items_proceso")
            .select("id")
            .eq("extraction_id", extraction_id)
            .execute()
            .data
        )
        for item in items:
            service_client.table("matching_candidatos").delete().eq(
                "item_proceso_id", item["id"]
            ).execute()
            service_client.table("items_proceso").update({"alias_id": None}).eq(
                "id", item["id"]
            ).execute()
        for item in items:
            service_client.table("items_proceso").delete().eq("id", item["id"]).execute()

        # 0025 (Phase 5): ordenes_compra.extraction_id (fk_oc_extr) no tiene
        # ON DELETE CASCADE -- si esta extracción fue el ancla de una
        # confirmación de orden de compra (D13.1 § Confirmación), hay que
        # borrar esa fila (y su cascada oc_items/entregas_oc/
        # entregas_oc_items, y su historial_cambios sin cascade) antes de
        # poder borrar extraction_results.
        ordenes = (
            service_client.table("ordenes_compra")
            .select("id")
            .eq("extraction_id", extraction_id)
            .execute()
            .data
        )
        for oc in ordenes:
            _borrar_orden_compra_en_cascada(service_client, orden_compra_id=oc["id"])

        service_client.table("extraction_results").delete().eq("id", extraction_id).execute()
