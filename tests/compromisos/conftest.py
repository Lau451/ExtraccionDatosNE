import secrets
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from services.shared.config import get_settings
from tests.oc_entregas.fixtures import caso_planificacion


def hoy_buenos_aires() -> date:
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/oc_export/conftest.py::crear_usuario_con_token (un conftest.py de
    un árbol hermano no es visible acá). JWT real: el router lee con el client del usuario, así
    que estos tests SÍ ejercitan la RLS de la vista y de sus tablas base."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"compromisos-test-{uuid.uuid4()}@seed.local"
        password = secrets.token_urlsafe(24)
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        creados.append(usuario_id)
        service_client.table("usuarios").insert(
            {
                "id": usuario_id,
                "drogueria_id": drogueria_id,
                "rol": rol,
                "nombre": "Compromisos test",
                "es_sistema": rol == "sistema",  # ck_usuarios_es_sistema
            }
        ).execute()

        cliente_temporal = create_client(settings.supabase_url, settings.supabase_anon_key)
        sesion = cliente_temporal.auth.sign_in_with_password({"email": email, "password": password})
        return usuario_id, sesion.session.access_token

    yield _crear
    for usuario_id in creados:
        service_client.auth.admin.delete_user(usuario_id)


@pytest.fixture
def otra_drogueria(service_client):
    cuit = f"20-{secrets.randbelow(99_999_999):08d}-9"
    drogueria = (
        service_client.table("droguerias")
        .insert(
            {
                "nombre": "Droguería Otra (compromisos test)",
                "razon_social": "Droguería Otra SA",
                "cuit": cuit,
                "ciudad": "Rosario",
                "provincia": "Santa Fe",
                "contacto_email": f"otra-{uuid.uuid4()}@seed.local",
                "contacto_telefono": "0000000000",
            }
        )
        .execute()
        .data[0]
    )
    yield drogueria
    service_client.table("droguerias").delete().eq("id", drogueria["id"]).execute()


@pytest.fixture
def sembrar_oc_con_plan(service_client, crear_usuario_con_token):
    """Factory: OC con un plan de entregas (sin exportar) en la droguería dada. Devuelve el caso
    de caso_planificacion con `entregas` (por número). Depende de `crear_usuario_con_token` para
    que este teardown corra ANTES del borrado de usuarios (`exportado_por` referencia a
    `usuarios`)."""
    casos: list[dict] = []

    def _sembrar(*, drogueria_id: str, plan: list[tuple[int, date, list[tuple[str, str]]]]) -> dict:
        caso = caso_planificacion.sembrar(service_client, drogueria_id=drogueria_id)
        casos.append(caso)
        caso["entregas"] = {}
        for numero, fecha, items in plan:
            clave_items = [(caso[clave]["id"], cantidad) for clave, cantidad in items]
            entrega = (
                service_client.table("entregas_oc")
                .insert(
                    {
                        "orden_compra_id": caso["orden_compra_id"],
                        "drogueria_id": drogueria_id,
                        "numero_entrega": numero,
                        "fecha_entrega_planificada": fecha.isoformat(),
                        "cantidad_items": len(clave_items),
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
                    for oc_item_id, cantidad in clave_items
                ]
            ).execute()
            caso["entregas"][numero] = entrega
        return caso

    yield _sembrar
    for caso in casos:
        service_client.table("historial_cambios").delete().eq(
            "orden_compra_id", caso["orden_compra_id"]
        ).execute()
        # 0033: el trigger congela el plan de una OC exportada; se desmarca antes de limpiar().
        service_client.table("ordenes_compra").update(
            {"exportado_at": None, "exportado_por": None, "archivo_exportado": None}
        ).eq("id", caso["orden_compra_id"]).execute()
        caso_planificacion.limpiar(service_client, caso)


@pytest.fixture
def marcar_exportada(service_client):
    def _marcar(caso: dict, *, usuario_id: str) -> None:
        service_client.table("ordenes_compra").update(
            {
                "exportado_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "exportado_por": usuario_id,
                "archivo_exportado": "OC_TEST.csv",
            }
        ).eq("id", caso["orden_compra_id"]).execute()

    return _marcar


def dias(delta: int) -> date:
    return hoy_buenos_aires() + timedelta(days=delta)
