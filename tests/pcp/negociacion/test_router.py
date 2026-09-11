"""7.7 (openspec/changes/gestor-pcp/tasks.md Fase 7) -- pcp-negociacion
router: require_roles() rechaza un rol no autorizado antes de que el
servicio toque `precios_proveedor`/`pcp_renglon_resultados`; un rol
autorizado sí puede registrar el resultado.

Mismo criterio que tests/pcp/catalogo/test_router.py (6.5) y
tests/pcp/gestion/test_router.py (4.9): ciclo HTTP completo (TestClient + JWT
real) porque invocar la función del endpoint directamente en Python no
ejercita `Depends(require_roles(...))`. Este PR no monta
`services/pcp/negociacion/router.py` en `main.py` por su cuenta -- eso lo
hace el agregador (`services/pcp/router.py`) -- así que se arma una
`FastAPI()` descartable solo para este test.
"""

from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.negociacion.router import router
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon, seleccionar_proveedores
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.integration
def test_registrar_resultado_con_rol_no_autorizado_es_rechazado_sin_escribir_nada(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
    crear_usuario_con_token,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        # "comercial" no está en ROLES_ESCRITURA_PCP (D11: solo admin/gerencia/compras).
        _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
        client = _cliente_de_prueba()

        respuesta = client.post(
            f"/pcp/{pcp['id']}/renglones/{renglon['id']}/proveedores/{seed_proveedor_pcp['id']}/resultado",
            json={
                "resultado": "precio_obtenido",
                "precio_unitario": "10.00",
                "mantenimiento_hasta": (date.today() + timedelta(days=10)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 403
        en_bd = (
            service_client.table("precios_proveedor")
            .select("id")
            .eq("item_proceso_id", seed_item_proceso["id"])
            .execute()
            .data
        )
        assert en_bd == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_registrar_resultado_con_rol_autorizado_devuelve_200_y_registra_el_resultado(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
    crear_usuario_con_token,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
        client = _cliente_de_prueba()

        respuesta = client.post(
            f"/pcp/{pcp['id']}/renglones/{renglon['id']}/proveedores/{seed_proveedor_pcp['id']}/resultado",
            json={
                "resultado": "precio_obtenido",
                "precio_unitario": "10.00",
                "mantenimiento_hasta": (date.today() + timedelta(days=10)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code < 300
        cuerpo = respuesta.json()
        assert cuerpo["resultado"] == "precio_obtenido"
        assert cuerpo["precio_proveedor_id"] is not None
    finally:
        # pcp primero: cascadea a pcp_renglon_resultados (fk_ppr_renglon ON
        # DELETE CASCADE vía pcp_renglones), liberando fk_ppr_precio_prov
        # antes de poder borrar la fila de precios_proveedor.
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()


@pytest.mark.integration
def test_obtener_resultado_endpoint_incluye_precio_y_condiciones_joined(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
    crear_usuario_con_token,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
        client = _cliente_de_prueba()
        vencimiento = (date.today() + timedelta(days=10)).isoformat()

        registro = client.post(
            f"/pcp/{pcp['id']}/renglones/{renglon['id']}/proveedores/{seed_proveedor_pcp['id']}/resultado",
            json={
                "resultado": "precio_obtenido",
                "precio_unitario": "10.00",
                "mantenimiento_hasta": vencimiento,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert registro.status_code < 300

        respuesta = client.get(
            f"/pcp/{pcp['id']}/renglones/{renglon['id']}/proveedores/{seed_proveedor_pcp['id']}/resultado",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code < 300
        cuerpo = respuesta.json()
        assert cuerpo["precio_unitario"] == "10.00" or float(cuerpo["precio_unitario"]) == 10.00
        assert cuerpo["mantenimiento_hasta"] == vencimiento
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()


@pytest.mark.integration
def test_actualizar_seleccion_rechaza_rol_solo_lectura_sin_modificar_resultado(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
    crear_usuario_con_token,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(service_client, drogueria_id=seed_drogueria["id"], body=PcpCreate(presupuesto_id=presupuesto["id"]), usuario_id=seed_usuario_sistema["id"])
    renglon = crear_renglon(service_client, drogueria_id=seed_drogueria["id"], pcp_id=pcp["id"], body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]), usuario_id=seed_usuario_sistema["id"])
    seleccionar_proveedores(service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"], proveedor_ids=[seed_proveedor_pcp["id"]])
    try:
        _, token = crear_usuario_con_token(rol="superadmin", drogueria_id=seed_drogueria["id"])
        respuesta = _cliente_de_prueba().patch(
            f"/pcp/{pcp['id']}/renglones/{renglon['id']}/proveedores/{seed_proveedor_pcp['id']}/seleccion",
            json={"seleccionado": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert respuesta.status_code == 403
        fila = service_client.table("pcp_renglon_resultados").select("seleccionado").eq("pcp_renglon_id", renglon["id"]).execute().data[0]
        assert fila["seleccionado"] is False
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_actualizar_seleccion_y_agregado_devuelven_renglon_unico(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
    crear_usuario_con_token,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(service_client, drogueria_id=seed_drogueria["id"], body=PcpCreate(presupuesto_id=presupuesto["id"]), usuario_id=seed_usuario_sistema["id"])
    renglon = crear_renglon(service_client, drogueria_id=seed_drogueria["id"], pcp_id=pcp["id"], body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]), usuario_id=seed_usuario_sistema["id"])
    seleccionar_proveedores(service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"], proveedor_ids=[seed_proveedor_pcp["id"]])
    try:
        _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
        client = _cliente_de_prueba()
        ruta = f"/pcp/{pcp['id']}/renglones/{renglon['id']}/proveedores/{seed_proveedor_pcp['id']}/seleccion"
        respuesta = client.patch(ruta, json={"seleccionado": True}, headers={"Authorization": f"Bearer {token}"})
        assert respuesta.status_code < 300
        assert respuesta.json()["seleccionado"] is True
        agregado = client.get(f"/pcp/{pcp['id']}/seleccion", headers={"Authorization": f"Bearer {token}"})
        assert agregado.status_code < 300
        assert agregado.json() == [renglon["id"]]
        desconocido = client.patch(ruta.replace(seed_proveedor_pcp["id"], "00000000-0000-0000-0000-000000000000"), json={"seleccionado": True}, headers={"Authorization": f"Bearer {token}"})
        assert desconocido.status_code == 404
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# Corrective Rerun -- GET /pcp/{pcp_id}/selecciones-agrupables (read-role
# access to the renglón×proveedor pairs that feed grouping into
# consultations; see openspec/changes/pcp-frontend apply-progress.md
# "Corrective Rerun -- Consultas grouping scope").
@pytest.mark.integration
def test_selecciones_agrupables_endpoint_permite_rol_lectura(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
    crear_usuario_con_token,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(service_client, drogueria_id=seed_drogueria["id"], body=PcpCreate(presupuesto_id=presupuesto["id"]), usuario_id=seed_usuario_sistema["id"])
    renglon = crear_renglon(service_client, drogueria_id=seed_drogueria["id"], pcp_id=pcp["id"], body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]), usuario_id=seed_usuario_sistema["id"])
    seleccionar_proveedores(service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"], proveedor_ids=[seed_proveedor_pcp["id"]])
    try:
        client = _cliente_de_prueba()
        _, token_escritura = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
        ruta_seleccion = f"/pcp/{pcp['id']}/renglones/{renglon['id']}/proveedores/{seed_proveedor_pcp['id']}/seleccion"
        marcado = client.patch(ruta_seleccion, json={"seleccionado": True}, headers={"Authorization": f"Bearer {token_escritura}"})
        assert marcado.status_code < 300

        _, token_lectura = crear_usuario_con_token(rol="gerencia", drogueria_id=seed_drogueria["id"])
        respuesta = client.get(
            f"/pcp/{pcp['id']}/selecciones-agrupables",
            headers={"Authorization": f"Bearer {token_lectura}"},
        )
        assert respuesta.status_code < 300
        assert respuesta.json() == [
            {"pcp_renglon_id": renglon["id"], "proveedor_id": seed_proveedor_pcp["id"]}
        ]
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
