"""12.2 (openspec/changes/gestor-pcp/tasks.md Fase 12) -- matriz de roles E2E
sobre TODOS los routers reales de `services/pcp/`, montados en la app real
(`services.presupuestacion.main:app`) -- a diferencia de los tests de router
por submódulo (4.9/5.6/6.5/7.7/9.7/10.4), que arman una `FastAPI()`
descartable con un solo router incluido. Esta suite confirma que el
agregador (`services/pcp/router.py`) y el montaje final en `main.py`
(`services/presupuestacion/main.py`) no dejan ningún endpoint sin el gate de
`ROLES_LECTURA_PCP`/`ROLES_ESCRITURA_PCP` (design.md D11) -- `pcp-historial`
no tiene router propio (ver docstring de `services/pcp/router.py`), así que
queda fuera de esta matriz a propósito.

D11: `ROLES_LECTURA_PCP = (superadmin, admin, gerencia, compras)`;
`ROLES_ESCRITURA_PCP = (admin, gerencia, compras)` -- `superadmin` puede leer
pero NO escribir. "comercial"/"lider_comercial" no están en ninguno de los
dos conjuntos (no ven pantallas de PCP en absoluto).

Decisión de alcance de esta suite: cubre exhaustivamente el caso de RECHAZO
(rol no autorizado -> 403, sin fila creada/modificada) en los diez GET y
los nueve POST/PATCH de `services/pcp/`, más un control positivo liviano de
lectura (rol autorizado -> no 403) para confirmar que los conjuntos de roles
no quedaron sobre-restringidos. El camino "rol autorizado logra escribir"
para cada endpoint de escritura NO se repite acá -- ya está probado, uno por
uno, en `tests/pcp/*/test_router.py` (4.9/5.6/6.5/7.7/9.3/9.7/11.5/11.8/
11.10); duplicarlo acá multiplicaría el costo de esta matriz (crear usuarios
reales, PDFs, emails) sin agregar cobertura nueva.

Fixture de datos (`mundo`) y de tokens (`tokens`) en scope `module`, no
`function`: cada uno de los ~58 casos de esta matriz espera que
`Depends(require_roles(...))` corte ANTES de que el servicio toque la base
-- compartir el mismo universo de datos y los mismos cuatro usuarios (uno
por rol relevante) entre casos es seguro exactamente porque ninguno de ellos
debería modificar nada, y evita rearmar un PCP completo (~8 inserts) y crear
un usuario nuevo por cada combinación de rol/endpoint.
"""

import secrets
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from supabase import create_client

from services.pcp.consultas.models import AgruparConsultaCreate, SeleccionParaAgrupar
from services.pcp.consultas.service import agrupar_renglones
from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.negociacion.models import RegistrarResultadoNegociacion
from services.pcp.negociacion.service import registrar_resultado
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon, seleccionar_proveedores
from services.pcp.roles import ROLES_ESCRITURA_PCP, ROLES_LECTURA_PCP
from services.presupuestacion.main import app
from services.shared.config import get_settings

ROL_SIN_ACCESO = "comercial"  # fuera de ROLES_LECTURA_PCP y ROLES_ESCRITURA_PCP (D11)
ROL_SIN_ACCESO_2 = "lider_comercial"  # idem -- segundo rol, para no depender de uno solo
ROL_SOLO_LECTURA = "superadmin"  # en ROLES_LECTURA_PCP, fuera de ROLES_ESCRITURA_PCP
ROL_LECTURA_Y_ESCRITURA = "compras"  # en ambos conjuntos


def _cliente_real() -> TestClient:
    return TestClient(app)


def test_conjuntos_de_roles_son_los_documentados_en_d11():
    """Sanity check unitario (no integración): si `services/pcp/roles.py`
    cambia de forma, toda esta suite cambia de significado sin que ningún
    otro test lo note -- design.md D11 es explícito sobre estos dos
    conjuntos exactos, y esta matriz asume exactamente esta forma."""
    assert set(ROLES_LECTURA_PCP) == {"superadmin", "admin", "gerencia", "compras"}
    assert set(ROLES_ESCRITURA_PCP) == {"admin", "gerencia", "compras"}
    assert ROL_SIN_ACCESO not in ROLES_LECTURA_PCP
    assert ROL_SIN_ACCESO_2 not in ROLES_LECTURA_PCP
    assert ROL_SOLO_LECTURA in ROLES_LECTURA_PCP and ROL_SOLO_LECTURA not in ROLES_ESCRITURA_PCP
    assert ROL_LECTURA_Y_ESCRITURA in ROLES_LECTURA_PCP and ROL_LECTURA_Y_ESCRITURA in ROLES_ESCRITURA_PCP


@pytest.fixture(scope="module")
def mundo(service_client):
    """Universo de datos compartido por toda la matriz: una sola droguería,
    un PCP completamente armado (header, renglón, proveedor catalogado,
    selección, resultado `precio_obtenido`, consulta agrupada) más recursos
    "libres" (presupuesto/renglón/proveedor sin asociar) para las
    verificaciones de creación de los endpoints POST. No reusa los fixtures
    `seed_*` de `tests/conftest.py`/`tests/pcp/conftest.py` (todos scope
    `function`) porque pytest no permite que un fixture `module` dependa de
    uno `function` -- `service_client` es el único fixture compartido acá,
    y ya es scope `session`."""
    cuit = f"20-{secrets.randbelow(99_999_999):08d}-9"
    drogueria = (
        service_client.table("droguerias")
        .insert(
            {
                "nombre": "Droguería Matriz PCP",
                "razon_social": "Droguería Matriz PCP SA",
                "cuit": cuit,
                "ciudad": "Rosario",
                "provincia": "Santa Fe",
                "contacto_email": f"seed-{uuid.uuid4()}@seed.local",
                "contacto_telefono": "0000000000",
            }
        )
        .execute()
        .data[0]
    )
    proceso = (
        service_client.table("procesos_comerciales")
        .insert({"drogueria_id": drogueria["id"], "clase": "cotizacion", "nombre": "Proceso matriz PCP"})
        .execute()
        .data[0]
    )
    producto = (
        service_client.table("productos")
        .insert(
            {
                "drogueria_id": drogueria["id"],
                "codigo_interno": f"TEST-{uuid.uuid4().hex[:8]}",
                "nombre": "Producto matriz PCP",
            }
        )
        .execute()
        .data[0]
    )
    auth_sistema = service_client.auth.admin.create_user(
        {
            "email": f"sistema-matriz-pcp-{uuid.uuid4()}@seed.local",
            "password": secrets.token_urlsafe(24),
            "email_confirm": True,
        }
    )
    usuario_sistema_id = auth_sistema.user.id
    service_client.table("usuarios").insert(
        {
            "id": usuario_sistema_id,
            "drogueria_id": None,
            "rol": "sistema",
            "nombre": "Sistema (matriz PCP)",
            "es_sistema": True,
        }
    ).execute()

    def _item_proceso(numero: int) -> dict:
        return (
            service_client.table("items_proceso")
            .insert(
                {
                    "proceso_comercial_id": proceso["id"],
                    "drogueria_id": drogueria["id"],
                    "numero_renglon": numero,
                    "descripcion": f"Renglón matriz {numero}",
                    "cantidad": "10",
                    "producto_id": producto["id"],
                }
            )
            .execute()
            .data[0]
        )

    def _presupuesto() -> dict:
        return (
            service_client.table("presupuestos")
            .insert(
                {
                    "proceso_comercial_id": proceso["id"],
                    "drogueria_id": drogueria["id"],
                    "estado": "generado",
                    "monto_total": "0",
                    "cantidad_items": 0,
                    "items_sin_precio": 0,
                }
            )
            .execute()
            .data[0]
        )

    def _proveedor(nombre: str) -> dict:
        tercero = (
            service_client.table("terceros")
            .insert({"drogueria_id": drogueria["id"], "razon_social": nombre})
            .execute()
            .data[0]
        )
        return (
            service_client.table("proveedores")
            .insert({"id": tercero["id"], "drogueria_id": drogueria["id"], "es_proveedor_compra": True})
            .execute()
            .data[0]
        )

    item = _item_proceso(1)
    item_libre = _item_proceso(2)
    presupuesto = _presupuesto()
    presupuesto_libre = _presupuesto()
    proveedor = _proveedor("Proveedor Matriz PCP")
    proveedor_libre = _proveedor("Proveedor Matriz PCP (libre)")

    pcp = crear_pcp(
        service_client,
        drogueria_id=drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=usuario_sistema_id,
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item["id"]),
        usuario_id=usuario_sistema_id,
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=drogueria["id"],
        proveedor_ids=[proveedor["id"]],
    )
    registrar_resultado(
        service_client,
        drogueria_id=drogueria["id"],
        pcp_renglon_id=renglon["id"],
        proveedor_id=proveedor["id"],
        body=RegistrarResultadoNegociacion(
            resultado="precio_obtenido",
            precio_unitario=Decimal("10.00"),
            mantenimiento_hasta=date.today() + timedelta(days=10),
        ),
        usuario_id=usuario_sistema_id,
    )
    consultas = agrupar_renglones(
        service_client,
        drogueria_id=drogueria["id"],
        body=AgruparConsultaCreate(
            selecciones=[SeleccionParaAgrupar(pcp_renglon_id=renglon["id"], proveedor_id=proveedor["id"])]
        ),
        usuario_id=usuario_sistema_id,
    )

    ctx = {
        "drogueria_id": drogueria["id"],
        "pcp_id": pcp["id"],
        "renglon_id": renglon["id"],
        "producto_id": producto["id"],
        "proveedor_id": proveedor["id"],
        "proveedor_libre_id": proveedor_libre["id"],
        "consulta_id": consultas[0]["id"],
        "presupuesto_libre_id": presupuesto_libre["id"],
        "item_proceso_libre_id": item_libre["id"],
    }

    yield ctx

    # Orden de limpieza: `pcp` primero -- cascadea a `pcp_renglones` y de ahí
    # a `pcp_renglon_resultados`, liberando tanto `fk_ppr_precio_prov` (hacia
    # `precios_proveedor`) como `fk_ppr_consulta` (hacia `pcp_consultas`) --
    # mismo criterio que `tests/pcp/negociacion/test_router.py` /
    # `tests/pcp/consultas/test_router.py`. Recién después se puede borrar
    # `pcp_consultas` sin violar esa segunda FK.
    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
    service_client.table("precios_proveedor").delete().eq("item_proceso_id", item["id"]).execute()
    service_client.table("pcp_consultas").delete().eq("id", consultas[0]["id"]).execute()
    service_client.table("presupuestos").delete().in_(
        "id", [presupuesto["id"], presupuesto_libre["id"]]
    ).execute()
    service_client.table("items_proceso").delete().in_("id", [item["id"], item_libre["id"]]).execute()
    service_client.table("terceros").delete().eq("drogueria_id", drogueria["id"]).execute()
    service_client.auth.admin.delete_user(usuario_sistema_id)
    service_client.table("productos").delete().eq("id", producto["id"]).execute()
    service_client.table("historial_cambios").delete().eq("proceso_comercial_id", proceso["id"]).execute()
    service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()
    service_client.table("droguerias").delete().eq("id", drogueria["id"]).execute()


@pytest.fixture(scope="module")
def tokens(service_client, mundo):
    """Un usuario+token real por rol relevante a esta matriz (JWT real, no
    mockeado -- necesario para ejercitar `Depends(require_roles(...))` de
    verdad), creado UNA sola vez por módulo y reusado en los ~58 casos: el
    rol de cada usuario no cambia entre casos, así que crear un usuario
    nuevo por combinación sería un costo repetido sin ningún beneficio de
    aislamiento (ver docstring de `mundo` sobre por qué compartir es
    seguro)."""
    settings = get_settings()
    creados: list[str] = []
    cache: dict[str, str] = {}

    def _token(rol: str) -> str:
        if rol in cache:
            return cache[rol]
        email = f"pcp-matriz-{rol}-{uuid.uuid4()}@seed.local"
        password = secrets.token_urlsafe(24)
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        creados.append(usuario_id)
        # ck_usuarios_superadmin (docs/schema/extractor_final.sql) exige
        # drogueria_id IS NULL para el rol "superadmin" -- mismo criterio que
        # tests/usuarios/conftest.py::seed_superadmin. No afecta el gate que
        # esta suite ejercita (require_roles() rechaza por `rol`, antes de
        # mirar drogueria_id), solo el INSERT del usuario de prueba.
        service_client.table("usuarios").insert(
            {
                "id": usuario_id,
                "drogueria_id": None if rol == "superadmin" else mundo["drogueria_id"],
                "rol": rol,
                "nombre": f"Matriz PCP ({rol})",
            }
        ).execute()
        cliente_temporal = create_client(settings.supabase_url, settings.supabase_anon_key)
        sesion = cliente_temporal.auth.sign_in_with_password({"email": email, "password": password})
        cache[rol] = sesion.session.access_token
        return cache[rol]

    yield _token
    for usuario_id in creados:
        service_client.auth.admin.delete_user(usuario_id)


# ---------------------------------------------------------------------------
# GET (lectura) -- los diez endpoints de solo lectura de services/pcp/.
# ---------------------------------------------------------------------------
GET_ENDPOINTS = [
    ("listar_pcp", "/pcp"),
    ("obtener_pcp", "/pcp/{pcp_id}"),
    ("listar_renglones", "/pcp/{pcp_id}/renglones"),
    ("detalle_renglon", "/pcp/{pcp_id}/renglones/{renglon_id}"),
    ("catalogo_proveedores", "/pcp/catalogo/productos/{producto_id}/proveedores"),
    (
        "obtener_resultado",
        "/pcp/{pcp_id}/renglones/{renglon_id}/proveedores/{proveedor_id}/resultado",
    ),
    ("obtener_consulta", "/pcp/consultas/{consulta_id}"),
    ("pdf_consulta", "/pcp/consultas/{consulta_id}/pdf"),
    ("sugerencia_agrupacion", "/pcp/sugerencias/renglones/{renglon_id}/agrupacion"),
    ("sugerencia_precios_recientes", "/pcp/sugerencias/renglones/{renglon_id}/precios-recientes"),
]


@pytest.mark.integration
@pytest.mark.parametrize("rol", [ROL_SIN_ACCESO, ROL_SIN_ACCESO_2])
@pytest.mark.parametrize("nombre, path", GET_ENDPOINTS, ids=[n for n, _ in GET_ENDPOINTS])
def test_lectura_rol_no_autorizado_es_rechazada(nombre, path, rol, mundo, tokens):
    respuesta = _cliente_real().get(
        path.format(**mundo), headers={"Authorization": f"Bearer {tokens(rol)}"}
    )
    assert respuesta.status_code == 403, (
        f"{nombre} debería rechazar el rol {rol!r} (fuera de ROLES_LECTURA_PCP, D11)"
    )


# Defecto preexistente DESCUBIERTO por esta suite (no introducido por la
# Fase 12 -- viene de PR4/PR5/PR6): `listar_pcp`/`listar_renglones`/
# `listar_proveedores_producto` filtran incondicionalmente
# `.eq("drogueria_id", usuario.drogueria_id)` sin el bypass `es_superadmin`
# que sí tienen `obtener_pcp`/`cambiar_estado`/`cerrar_pcp` (D11:
# "superadmin keeps read access as the standing cross-tenant support-role
# convention"). Para "superadmin" (`drogueria_id` NULL en `usuarios`, exigido
# por `ck_usuarios_superadmin`), postgrest-py serializa ese `None` de Python
# como el literal `"None"` en el filtro `.eq(...)`, y Postgres lo rechaza con
# `invalid input syntax for type uuid: "None"` (22P02) -- una excepción sin
# traducir (`register_exception_handlers` no mapea `postgrest.exceptions.
# APIError`), así que el `TestClient` la re-lanza en vez de devolver una
# respuesta. `xfail(strict=True)` documenta el gap real -- mismo criterio que
# `D-TERCEROS-001` (docs/modulos/terceros/decisiones.md) -- en vez de
# silenciarlo u de ampliar el alcance de esta fase (docs + tests) a un fix de
# producción no pedido. Ver docs/modulos/pcp/decisiones.md D11 (Fase 12) para
# el seguimiento.
_GAP_LISTADO_SUPERADMIN = frozenset({"listar_pcp", "listar_renglones", "catalogo_proveedores"})


def _caso_lectura_autorizada(nombre: str, path: str, rol: str):
    if rol == ROL_SOLO_LECTURA and nombre in _GAP_LISTADO_SUPERADMIN:
        return pytest.param(
            nombre,
            path,
            rol,
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    f"{nombre} no aplica el bypass es_superadmin a su filtro de drogueria_id "
                    "(defecto preexistente, ver docs/modulos/pcp/decisiones.md D11)"
                ),
            ),
            id=f"{nombre}-{rol}",
        )
    return pytest.param(nombre, path, rol, id=f"{nombre}-{rol}")


LECTURA_AUTORIZADA_CASOS = [
    _caso_lectura_autorizada(nombre, path, rol)
    for rol in (ROL_SOLO_LECTURA, ROL_LECTURA_Y_ESCRITURA)
    for nombre, path in GET_ENDPOINTS
]


@pytest.mark.integration
@pytest.mark.parametrize("nombre, path, rol", LECTURA_AUTORIZADA_CASOS)
def test_lectura_rol_autorizado_no_es_rechazada(nombre, path, rol, mundo, tokens):
    respuesta = _cliente_real().get(
        path.format(**mundo), headers={"Authorization": f"Bearer {tokens(rol)}"}
    )
    assert respuesta.status_code != 403, (
        f"{nombre} no debería rechazar el rol {rol!r} (en ROLES_LECTURA_PCP, D11)"
    )


# ---------------------------------------------------------------------------
# POST/PATCH (escritura) -- los nueve endpoints de escritura de services/pcp/.
# Cada caso reusa una fila ya existente en `mundo` (o apunta a un recurso
# "libre" nunca tocado) para poder afirmar, después del 403, que ninguna fila
# fue creada ni modificada -- "sin_cambios" es la prueba de esa invariante.
# ---------------------------------------------------------------------------
WRITE_CASES = [
    {
        "nombre": "crear_pcp",
        "method": "POST",
        "path": "/pcp",
        "body": lambda ctx: {"presupuesto_id": ctx["presupuesto_libre_id"]},
        "sin_cambios": lambda sc, ctx: sc.table("pcp")
        .select("id")
        .eq("presupuesto_id", ctx["presupuesto_libre_id"])
        .execute()
        .data
        == [],
    },
    {
        "nombre": "cambiar_estado",
        "method": "PATCH",
        "path": "/pcp/{pcp_id}/estado",
        "body": lambda ctx: {"estado": "en_gestion"},
        "sin_cambios": lambda sc, ctx: sc.table("pcp").select("estado").eq("id", ctx["pcp_id"]).execute().data[
            0
        ]["estado"]
        == "nueva",
    },
    {
        "nombre": "crear_renglon",
        "method": "POST",
        "path": "/pcp/{pcp_id}/renglones",
        "body": lambda ctx: {"item_proceso_id": ctx["item_proceso_libre_id"]},
        "sin_cambios": lambda sc, ctx: sc.table("pcp_renglones")
        .select("id")
        .eq("item_proceso_id", ctx["item_proceso_libre_id"])
        .execute()
        .data
        == [],
    },
    {
        "nombre": "seleccionar_proveedores",
        "method": "POST",
        "path": "/pcp/{pcp_id}/renglones/{renglon_id}/proveedores",
        "body": lambda ctx: {"proveedor_ids": [ctx["proveedor_id"]]},
        "sin_cambios": lambda sc, ctx: len(
            sc.table("pcp_renglon_resultados")
            .select("id")
            .eq("pcp_renglon_id", ctx["renglon_id"])
            .execute()
            .data
        )
        == 1,
    },
    {
        "nombre": "agregar_proveedor_catalogo",
        "method": "POST",
        "path": "/pcp/catalogo/productos/{producto_id}/proveedores",
        "body": lambda ctx: {"proveedor_id": ctx["proveedor_libre_id"]},
        "sin_cambios": lambda sc, ctx: sc.table("producto_proveedores")
        .select("id")
        .eq("proveedor_id", ctx["proveedor_libre_id"])
        .execute()
        .data
        == [],
    },
    {
        "nombre": "registrar_resultado",
        "method": "POST",
        "path": "/pcp/{pcp_id}/renglones/{renglon_id}/proveedores/{proveedor_id}/resultado",
        "body": lambda ctx: {"resultado": "no_cotiza"},
        "sin_cambios": lambda sc, ctx: sc.table("pcp_renglon_resultados")
        .select("resultado")
        .eq("pcp_renglon_id", ctx["renglon_id"])
        .eq("proveedor_id", ctx["proveedor_id"])
        .execute()
        .data[0]["resultado"]
        == "precio_obtenido",
    },
    {
        "nombre": "cerrar_pcp",
        "method": "POST",
        "path": "/pcp/{pcp_id}/cerrar",
        "body": lambda ctx: {},
        "sin_cambios": lambda sc, ctx: sc.table("pcp").select("estado").eq("id", ctx["pcp_id"]).execute().data[
            0
        ]["estado"]
        == "nueva",
    },
    {
        "nombre": "agrupar_renglones",
        "method": "POST",
        "path": "/pcp/consultas",
        "body": lambda ctx: {
            "selecciones": [{"pcp_renglon_id": ctx["renglon_id"], "proveedor_id": ctx["proveedor_id"]}]
        },
        "sin_cambios": lambda sc, ctx: len(
            sc.table("pcp_consultas").select("id").eq("proveedor_id", ctx["proveedor_id"]).execute().data
        )
        == 1,
    },
    {
        "nombre": "enviar_consulta",
        "method": "POST",
        "path": "/pcp/consultas/{consulta_id}/enviar",
        "body": lambda ctx: {},
        "sin_cambios": lambda sc, ctx: sc.table("pcp_consultas")
        .select("estado")
        .eq("id", ctx["consulta_id"])
        .execute()
        .data[0]["estado"]
        == "borrador",
    },
]


@pytest.mark.integration
@pytest.mark.parametrize("rol", [ROL_SIN_ACCESO, ROL_SOLO_LECTURA])
@pytest.mark.parametrize("caso", WRITE_CASES, ids=[c["nombre"] for c in WRITE_CASES])
def test_escritura_rol_no_autorizado_es_rechazada_sin_modificar(caso, rol, mundo, tokens, service_client):
    respuesta = _cliente_real().request(
        caso["method"],
        caso["path"].format(**mundo),
        json=caso["body"](mundo),
        headers={"Authorization": f"Bearer {tokens(rol)}"},
    )
    razon = (
        "fuera de ROLES_LECTURA_PCP" if rol == ROL_SIN_ACCESO else "en ROLES_LECTURA_PCP pero fuera de ROLES_ESCRITURA_PCP"
    )
    assert respuesta.status_code == 403, f"{caso['nombre']} debería rechazar el rol {rol!r} ({razon}, D11)"
    assert caso["sin_cambios"](
        service_client, mundo
    ), f"{caso['nombre']} no debería haber creado/modificado ninguna fila para el rol rechazado {rol!r}"
