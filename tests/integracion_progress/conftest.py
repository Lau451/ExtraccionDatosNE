import secrets
import uuid

import pytest

from services.shared.config import get_settings


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Usuario real + JWT para ejercitar `Depends(require_roles(...))` en un ciclo HTTP
    completo. Copia local del fixture de tests/pcp/imports/conftest.py (pytest solo ve
    los conftest.py de los directorios ancestros)."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"integracion-progress-test-{uuid.uuid4()}@seed.local"
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
def limpiar_progress_archivos(service_client, seed_drogueria, crear_usuario_con_token):
    """progress_archivos referencia droguerias y usuarios sin CASCADE (0043): sus filas
    se borran antes que el usuario y la droguería de test (este fixture depende de
    ambos, así que su teardown corre primero)."""
    yield
    service_client.table("progress_archivos").delete().eq(
        "drogueria_id", seed_drogueria["id"]
    ).execute()


@pytest.fixture
def seed_cliente_progress(service_client, seed_drogueria):
    """Cliente con `codigo_interno` conocido (tercero + fila de rol `clientes`, mismo
    alta en dos pasos que tests/pcp/imports/conftest.py::seed_cliente_pcp_factory).
    Borrar los terceros de la droguería cascadea a `clientes`."""

    def _seed(*, codigo_interno: str) -> dict:
        tercero = (
            service_client.table("terceros")
            .insert(
                {
                    "drogueria_id": seed_drogueria["id"],
                    "codigo_interno": codigo_interno,
                    "razon_social": "Cliente Integración Progress Test",
                }
            )
            .execute()
            .data[0]
        )
        return (
            service_client.table("clientes")
            .insert({"id": tercero["id"], "drogueria_id": seed_drogueria["id"], "tipo": "otro"})
            .execute()
            .data[0]
        )

    yield _seed
    service_client.table("terceros").delete().eq("drogueria_id", seed_drogueria["id"]).execute()
