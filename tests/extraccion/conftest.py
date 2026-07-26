import csv as csv_module
import secrets
import uuid

import pytest


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

        service_client.table("extraction_results").delete().eq("id", extraction_id).execute()
