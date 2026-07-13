import secrets
import uuid

import pytest

from presupuestacion.core.config import get_settings
from presupuestacion.core.database import get_service_client

_PROYECTO_TEST_ESPERADO = "grnamollopxdlstcpxhc"


@pytest.fixture(scope="session", autouse=True)
def _bloquear_si_no_es_bd_de_test():
    if _PROYECTO_TEST_ESPERADO not in get_settings().supabase_url:
        pytest.exit(
            f"SUPABASE_URL no apunta al proyecto de test ({_PROYECTO_TEST_ESPERADO}) — "
            "abortando para no correr tests de integración contra producción.",
            returncode=1,
        )


@pytest.fixture(scope="session")
def service_client():
    return get_service_client()


@pytest.fixture
def seed_drogueria(service_client):
    cuit = f"20-{secrets.randbelow(99_999_999):08d}-9"
    fila = {
        "nombre": "Droguería Test",
        "razon_social": "Droguería Test SA",
        "cuit": cuit,
        "ciudad": "Rosario",
        "provincia": "Santa Fe",
        "contacto_email": f"seed-{uuid.uuid4()}@seed.local",
        "contacto_telefono": "0000000000",
    }
    drogueria = service_client.table("droguerias").insert(fila).execute().data[0]
    yield drogueria
    service_client.table("droguerias").delete().eq("id", drogueria["id"]).execute()


@pytest.fixture
def seed_proceso_comercial(service_client, seed_drogueria):
    fila = {
        "drogueria_id": seed_drogueria["id"],
        "clase": "cotizacion",
        "nombre": "Proceso de test",
    }
    proceso = service_client.table("procesos_comerciales").insert(fila).execute().data[0]
    yield proceso
    service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()


@pytest.fixture
def seed_producto(service_client, seed_drogueria):
    fila = {
        "drogueria_id": seed_drogueria["id"],
        "codigo_interno": f"TEST-{uuid.uuid4().hex[:8]}",
        "nombre": "Producto de test",
    }
    producto = service_client.table("productos").insert(fila).execute().data[0]
    yield producto
    service_client.table("productos").delete().eq("id", producto["id"]).execute()


@pytest.fixture
def seed_proveedor(service_client, seed_drogueria):
    fila = {"drogueria_id": seed_drogueria["id"], "razon_social": "Proveedor de test"}
    proveedor = service_client.table("proveedores").insert(fila).execute().data[0]
    yield proveedor
    service_client.table("proveedores").delete().eq("id", proveedor["id"]).execute()


@pytest.fixture
def seed_usuario_sistema(service_client):
    email = f"sistema-test-{uuid.uuid4()}@seed.local"
    auth_response = service_client.auth.admin.create_user(
        {"email": email, "password": secrets.token_urlsafe(24), "email_confirm": True}
    )
    usuario_id = auth_response.user.id
    fila = {
        "id": usuario_id,
        "drogueria_id": None,
        "rol": "sistema",
        "nombre": "Usuario Sistema (test)",
        "es_sistema": True,
    }
    service_client.table("usuarios").insert(fila).execute()
    yield {"id": usuario_id, "rol": "sistema"}
    service_client.auth.admin.delete_user(usuario_id)
