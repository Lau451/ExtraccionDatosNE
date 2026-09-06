import secrets
import uuid

import pytest

from services.shared.config import get_settings


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/pcp/gestion/conftest.py::crear_usuario_con_token
    -- mismo motivo que seed_item_proceso más abajo (conftest.py de un árbol
    hermano no es visible acá). Necesaria para 5.6's router test: un JWT real
    para ejercitar `Depends(require_roles(...))` a través de un ciclo HTTP
    completo, no invocando el endpoint directamente en Python."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"pcp-renglones-router-test-{uuid.uuid4()}@seed.local"
        password = secrets.token_urlsafe(24)
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        creados.append(usuario_id)
        service_client.table("usuarios").insert(
            {"id": usuario_id, "drogueria_id": drogueria_id, "rol": rol, "nombre": "Router test"}
        ).execute()

        cliente_temporal = create_client(settings.supabase_url, settings.supabase_anon_key)
        sesion = cliente_temporal.auth.sign_in_with_password({"email": email, "password": password})
        return usuario_id, sesion.session.access_token

    yield _crear
    for usuario_id in creados:
        service_client.auth.admin.delete_user(usuario_id)


@pytest.fixture
def seed_item_proceso(service_client, seed_proceso_comercial, seed_producto, seed_drogueria):
    """Copia local de tests/pricing/conftest.py::seed_item_proceso -- no se
    reutiliza esa fixture directamente porque tests/pricing/conftest.py no
    está en el árbol de conftest visible para tests/pcp/ (pytest solo
    descubre conftest.py en directorios ancestros del test, no en árboles
    hermanos)."""
    fila = {
        "proceso_comercial_id": seed_proceso_comercial["id"],
        "drogueria_id": seed_drogueria["id"],
        "numero_renglon": 1,
        "descripcion": "Renglón de test",
        "cantidad": "10",
        "producto_id": seed_producto["id"],
    }
    item = service_client.table("items_proceso").insert(fila).execute().data[0]
    yield item
    service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


@pytest.fixture
def seed_item_proceso_sin_producto(service_client, seed_proceso_comercial, seed_drogueria):
    """Ítem de proceso sin `producto_id` -- para probar que el detalle de un
    renglón sin producto matcheado no intenta resolverlo (5.3, triangulación
    del caso `producto_id IS NULL`)."""
    fila = {
        "proceso_comercial_id": seed_proceso_comercial["id"],
        "drogueria_id": seed_drogueria["id"],
        "numero_renglon": 2,
        "descripcion": "Renglón sin producto matcheado",
        "cantidad": "5",
    }
    item = service_client.table("items_proceso").insert(fila).execute().data[0]
    yield item
    service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


@pytest.fixture
def limpiar_presupuestos(service_client):
    """Copia local de tests/pricing/conftest.py::limpiar_presupuestos --
    mismo motivo que seed_item_proceso arriba (conftest.py de un árbol
    hermano no es visible acá). 5.2 llama a `generar_presupuesto_para_endpoint`
    dos veces sobre el mismo `proceso_comercial_id` para simular una
    regeneración real (RN-PRICING-008); esta fixture limpia el presupuesto y
    sus `presupuesto_items`/`historial_cambios` al finalizar."""
    ids: list[str] = []
    yield ids
    for presupuesto_id in ids:
        service_client.table("historial_cambios").delete().eq("presupuesto_id", presupuesto_id).execute()
        service_client.table("presupuesto_items").delete().eq("presupuesto_id", presupuesto_id).execute()
        service_client.table("presupuestos").delete().eq("id", presupuesto_id).execute()


@pytest.fixture
def seed_proveedores_pcp_factory(service_client, seed_drogueria, limpiar_pcp_terceros):
    """Variante N de tests/pcp/conftest.py::seed_proveedor_pcp -- 5.4 necesita
    varios proveedores simultáneos para probar "seleccionar todos los
    disponibles". `limpiar_pcp_terceros` (tests/pcp/conftest.py) ya limpia
    todos los `terceros` de la droguería de test al finalizar, cascadeando a
    `proveedores` (fk_prov_tercero), así que no hace falta trackear altas acá."""

    def _seed(cantidad: int) -> list[dict]:
        proveedores = []
        for i in range(cantidad):
            tercero = (
                service_client.table("terceros")
                .insert({"drogueria_id": seed_drogueria["id"], "razon_social": f"Proveedor PCP Test {i}"})
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
            proveedores.append(proveedor)
        return proveedores

    return _seed
