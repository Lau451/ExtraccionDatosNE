import secrets
import uuid

import pytest

from services.shared.config import get_settings


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/pcp/gestion/conftest.py::crear_usuario_con_token
    -- mismo motivo que el resto de las copias locales en tests/pcp/*/conftest.py
    (conftest.py de un árbol hermano no es visible acá). Necesaria para el
    test de router: un JWT real para ejercitar `Depends(require_roles(...))`
    a través de un ciclo HTTP completo."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"pcp-negociacion-router-test-{uuid.uuid4()}@seed.local"
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
    """Copia local de tests/pcp/renglones/conftest.py::seed_item_proceso --
    mismo motivo (árbol hermano no visible). `producto_id` seteado: 7.2/7.8
    necesitan un renglón con producto ya matcheado para poder registrar un
    precio_obtenido (precios_proveedor.producto_id es NOT NULL)."""
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
def seed_item_proceso_factory(service_client, seed_proceso_comercial, seed_producto, seed_drogueria):
    """Variante N de `seed_item_proceso` -- 7.5 necesita dos renglones
    (A y B) sobre el mismo producto pero distinto `item_proceso_id`/
    `numero_renglon` para probar la invariante de aislamiento."""
    creados: list[dict] = []

    def _seed(*, numero_renglon: int, producto_id: str | None = None):
        fila = {
            "proceso_comercial_id": seed_proceso_comercial["id"],
            "drogueria_id": seed_drogueria["id"],
            "numero_renglon": numero_renglon,
            "descripcion": f"Renglón de test {numero_renglon}",
            "cantidad": "10",
            "producto_id": producto_id if producto_id is not None else seed_producto["id"],
        }
        item = service_client.table("items_proceso").insert(fila).execute().data[0]
        creados.append(item)
        return item

    yield _seed
    for item in creados:
        service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


@pytest.fixture
def seed_item_proceso_sin_producto(service_client, seed_proceso_comercial, seed_drogueria):
    """Copia local de tests/pcp/renglones/conftest.py::seed_item_proceso_sin_producto
    -- mismo motivo (árbol hermano no visible). Un renglón sobre este ítem no
    tiene `producto_id`, así que `precios_proveedor.producto_id` (NOT NULL)
    no puede resolverse -- ver test
    test_registrar_resultado_precio_obtenido_sin_producto_matcheado_lanza_validation_error."""
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
def seed_proveedores_pcp_factory(service_client, seed_drogueria, limpiar_pcp_terceros):
    """Copia local de tests/pcp/renglones/conftest.py::seed_proveedores_pcp_factory
    -- mismo motivo (árbol hermano no visible). `limpiar_pcp_terceros`
    (tests/pcp/conftest.py) ya limpia todos los `terceros` de la droguería de
    test al finalizar, cascadeando a `proveedores` (fk_prov_tercero)."""

    def _seed(cantidad: int) -> list[dict]:
        proveedores = []
        for i in range(cantidad):
            tercero = (
                service_client.table("terceros")
                .insert(
                    {"drogueria_id": seed_drogueria["id"], "razon_social": f"Proveedor Negociación Test {i}"}
                )
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


@pytest.fixture
def seed_solicitante_pcp(service_client, seed_drogueria):
    """PR11 (tasks.md 11.7/11.8) -- usuario "solicitante" de un PCP, con un
    email real capturado (a diferencia de `crear_usuario_con_token`, que solo
    devuelve `(usuario_id, token)`). `usuarios` no tiene columna `email`
    (vive en `auth.users`, rls_final.sql) -- `negociacion/repository.py::
    obtener_email_usuario` la resuelve vía la Admin API, así que el test
    necesita conocer de antemano qué email espera ver como destinatario."""
    email = f"pcp-solicitante-{uuid.uuid4()}@seed.local"
    auth_response = service_client.auth.admin.create_user(
        {"email": email, "password": secrets.token_urlsafe(24), "email_confirm": True}
    )
    usuario_id = auth_response.user.id
    service_client.table("usuarios").insert(
        {
            "id": usuario_id,
            "drogueria_id": seed_drogueria["id"],
            "rol": "comercial",
            "nombre": "Solicitante PCP Test",
        }
    ).execute()
    yield {"id": usuario_id, "email": email}
    service_client.auth.admin.delete_user(usuario_id)


@pytest.fixture
def seed_condicion_pago_pcp_factory(service_client, seed_drogueria):
    """Copia local del patrón de tests/terceros/conftest.py::seed_condicion_pago_factory
    -- mismo motivo de árbol hermano no visible. Sin cleanup por FK propio
    (services/pcp/negociacion no llega a esta fila): cada test que la usa la
    borra explícitamente, después de borrar cualquier `precios_proveedor`
    que la referencie (fk_pp_condpago)."""

    def _seed(nombre: str | None = None, **overrides):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "nombre": nombre or f"Condición PCP {uuid.uuid4().hex[:8]}",
            **overrides,
        }
        return service_client.table("condiciones_pago").insert(fila).execute().data[0]

    return _seed


@pytest.fixture
def seed_forma_pago_pcp_factory(service_client, seed_drogueria):
    """Copia local del patrón de tests/terceros/conftest.py::seed_forma_pago_factory."""

    def _seed(nombre: str | None = None, **overrides):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "nombre": nombre or f"Forma PCP {uuid.uuid4().hex[:8]}",
            **overrides,
        }
        return service_client.table("formas_pago").insert(fila).execute().data[0]

    return _seed
