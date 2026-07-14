import secrets
import uuid

import pytest
from supabase import Client

from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.database import get_service_client

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
def seed_proceso_comercial(service_client, seed_drogueria, seed_usuario_sistema):
    # Depende de seed_usuario_sistema (aunque no lo use en el setup) para garantizar que
    # el historial_cambios de este proceso -- que puede referenciar a usuario_sistema como
    # usuario_id si el test llama presentar_presupuesto -- se borre ANTES que el usuario.
    fila = {
        "drogueria_id": seed_drogueria["id"],
        "clase": "cotizacion",
        "nombre": "Proceso de test",
    }
    proceso = service_client.table("procesos_comerciales").insert(fila).execute().data[0]
    yield proceso
    # historial_cambios.proceso_comercial_id (fk_hc_proc) no tiene CASCADE -- hay que
    # borrar el historial antes que el proceso que referencia, ahora que presentar_presupuesto
    # audita el cambio de estado de procesos_comerciales.
    service_client.table("historial_cambios").delete().eq(
        "proceso_comercial_id", proceso["id"]
    ).execute()
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
def seed_producto_factory(service_client, seed_drogueria):
    creados = []

    def _seed(nombre: str = "Producto de test"):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "codigo_interno": f"TEST-{uuid.uuid4().hex[:8]}",
            "nombre": nombre,
        }
        producto = service_client.table("productos").insert(fila).execute().data[0]
        creados.append(producto)
        return producto

    yield _seed
    for producto in creados:
        service_client.table("productos").delete().eq("id", producto["id"]).execute()


@pytest.fixture
def seed_stock_factory(service_client, seed_drogueria):
    creados = []

    def _seed(producto_id: str, *, disponible: str, comprometida: str = "0", deposito: str | None = None):
        fila = {
            "producto_id": producto_id,
            "drogueria_id": seed_drogueria["id"],
            "deposito": deposito,
            "cantidad_disponible": disponible,
            "cantidad_comprometida": comprometida,
        }
        fila_stock = service_client.table("stock_productos").insert(fila).execute().data[0]
        creados.append(fila_stock)
        return fila_stock

    yield _seed
    for fila_stock in creados:
        service_client.table("stock_productos").delete().eq("id", fila_stock["id"]).execute()


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


@pytest.fixture
def crear_usuario_autenticado(service_client):
    """Factory que crea un usuario real (con password conocida) y devuelve un Client
    autenticado con su JWT real (anon key + sign_in_with_password), no service_client.
    Para tests que necesitan ejercitar RLS de verdad -- confirmar que una policy
    contiene, no solo que el filtro del código de aplicación funciona.

    Es la primera vez en el proyecto que se prueba RLS con un JWT real: hasta ahora
    todos los tests de integración usaban service_client, que bypasea RLS por
    completo, así que ninguna policy se había ejercitado de verdad, solo confirmado
    en el papel contra pg_policies. Nota para retomar (no bloquea nada de hoy): con
    este fixture disponible, valdría la pena agregar tests de aislamiento
    cross-tenant real -- confirmar empíricamente que un comercial de una droguería
    no puede ver/tocar datos de otra droguería, no solo que la policy lo diga."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, Client]:
        settings = get_settings()
        email = f"rls-test-{uuid.uuid4()}@seed.local"
        password = secrets.token_urlsafe(24)
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        creados.append(usuario_id)
        service_client.table("usuarios").insert(
            {"id": usuario_id, "drogueria_id": drogueria_id, "rol": rol, "nombre": "RLS test"}
        ).execute()

        cliente_autenticado = create_client(settings.supabase_url, settings.supabase_anon_key)
        sesion = cliente_autenticado.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        cliente_autenticado.postgrest.auth(sesion.session.access_token)
        return usuario_id, cliente_autenticado

    yield _crear
    for usuario_id in creados:
        service_client.auth.admin.delete_user(usuario_id)
