import secrets
import uuid

import pytest

from services.shared.config import get_settings
from tests.oc_entregas.fixtures import caso_planificacion


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/oc_entregas/conftest.py::crear_usuario_con_token (un
    conftest.py de un árbol hermano no es visible acá). JWT real para ejercitar
    `Depends(require_roles(...))` en un ciclo HTTP completo."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"oc-export-router-test-{uuid.uuid4()}@seed.local"
        password = secrets.token_urlsafe(24)
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        creados.append(usuario_id)
        service_client.table("usuarios").insert(
            {"id": usuario_id, "drogueria_id": drogueria_id, "rol": rol, "nombre": "Export test"}
        ).execute()

        cliente_temporal = create_client(settings.supabase_url, settings.supabase_anon_key)
        sesion = cliente_temporal.auth.sign_in_with_password({"email": email, "password": password})
        return usuario_id, sesion.session.access_token

    yield _crear
    for usuario_id in creados:
        service_client.auth.admin.delete_user(usuario_id)


@pytest.fixture
def caso_exportable(service_client, seed_drogueria, crear_usuario_con_token):
    """OC que cumple todas las precondiciones D2: 2 renglones con producto y código de
    artículo, un único código de cliente en `terceros_legacy_map` y un plan completo
    de 2 entregas con fecha.

    Depende de `crear_usuario_con_token` para que este teardown corra ANTES que el
    borrado de los usuarios: `ordenes_compra.exportado_por` referencia a `usuarios`."""
    caso = caso_planificacion.sembrar(service_client, drogueria_id=seed_drogueria["id"])
    drogueria_id = seed_drogueria["id"]
    sufijo = uuid.uuid4().hex[:8]
    producto_extra = (
        service_client.table("productos")
        .insert(
            {
                "drogueria_id": drogueria_id,
                "codigo_interno": f"OCX-TEST-{sufijo}",
                "nombre": "Producto extra (oc_export test)",
            }
        )
        .execute()
        .data[0]
    )
    service_client.table("oc_items").update({"producto_id": producto_extra["id"]}).eq(
        "id", caso["oc_item_sin_pack"]["id"]
    ).execute()
    service_client.table("terceros_legacy_map").insert(
        {
            "tercero_id": caso["tercero_id"],
            "drogueria_id": drogueria_id,
            "entidad_legacy": "cliente",
            "codigo_legacy": f"CLI{sufijo}",
        }
    ).execute()

    # (entrega, fecha, [(oc_item, cantidad)]): 110 = 60 + 50; 10 en la 1. El renglón 3 queda descartado y sin plan
    plan = [
        (1, "2026-10-15", [(caso["oc_item_con_pack"]["id"], "60"), (caso["oc_item_sin_pack"]["id"], "10")]),
        (2, "2026-11-15", [(caso["oc_item_con_pack"]["id"], "50")]),
    ]
    for numero, fecha, items in plan:
        entrega = (
            service_client.table("entregas_oc")
            .insert(
                {
                    "orden_compra_id": caso["orden_compra_id"],
                    "drogueria_id": drogueria_id,
                    "numero_entrega": numero,
                    "fecha_entrega_planificada": fecha,
                    "cantidad_items": len(items),
                    "estado": "pendiente",
                }
            )
            .execute()
            .data[0]
        )
        service_client.table("entregas_oc_items").insert(
            [
                {
                    "entrega_oc_id": entrega["id"],
                    "drogueria_id": drogueria_id,
                    "oc_item_id": oc_item_id,
                    "cantidad_planificada": cantidad,
                    "cantidad_entregada": "0",
                }
                for oc_item_id, cantidad in items
            ]
        ).execute()

    caso["codigo_cliente"] = f"CLI{sufijo}"
    try:
        yield caso
    finally:
        service_client.table("historial_cambios").delete().eq(
            "orden_compra_id", caso["orden_compra_id"]
        ).execute()
        caso_planificacion.limpiar(service_client, caso)
        service_client.table("productos").delete().eq("id", producto_extra["id"]).execute()
