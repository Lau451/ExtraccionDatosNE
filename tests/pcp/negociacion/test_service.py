"""7.2-7.6 (openspec/changes/gestor-pcp/tasks.md Fase 7) -- pcp-negociacion:
registrar un resultado de negociación precio_obtenido escribe una fila en
`precios_proveedor` (D4/D5) y transiciona el `pcp_renglon_resultados` que
PR5 dejó en `sin_respuesta`; no_cotiza no fabrica ninguna fila de precio ni
bloquea a otro proveedor del mismo renglón; la escritura respeta la
invariante de aislamiento (D2) y la ventana de vigencia de
`mantenimiento_hasta` (spec "Validity Window via mantenimiento_hasta").

RED hasta que 7.7 cree services/pcp/negociacion/service.py.
"""

from datetime import date, timedelta
from decimal import Decimal

from pydantic import ValidationError as PydanticValidationError
import pytest

from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.negociacion.models import (
    ActualizarSeleccionNegociacion,
    RegistrarResultadoNegociacion,
)
from services.pcp.negociacion.service import (
    actualizar_seleccion,
    listar_renglones_seleccionados,
    listar_resultados_renglon,
    listar_selecciones_agrupables,
    obtener_resultado,
    registrar_resultado,
)
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon, seleccionar_proveedores
from services.presupuestacion.pricing.repository import buscar_precio_especial_puntual
from services.shared.exceptions import NotFoundError, ValidationError as ServiceValidationError


def _crear_pcp_renglon_seleccionado(
    service_client, *, drogueria_id, presupuesto_id, item_proceso_id, usuario_id, proveedor_ids
):
    pcp = crear_pcp(
        service_client,
        drogueria_id=drogueria_id,
        body=PcpCreate(presupuesto_id=presupuesto_id),
        usuario_id=usuario_id,
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=drogueria_id,
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item_proceso_id),
        usuario_id=usuario_id,
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=drogueria_id,
        proveedor_ids=proveedor_ids,
    )
    return pcp, renglon


# ---------------------------------------------------------------------------
# 7.2 -- precio_obtenido escribe una fila en precios_proveedor scoped al
# item_proceso_id del renglón, y transiciona pcp_renglon_resultados
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_registrar_resultado_precio_obtenido_escribe_precios_proveedor_y_actualiza_resultado(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    vencimiento = date.today() + timedelta(days=30)
    resultado = registrar_resultado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        pcp_renglon_id=renglon["id"],
        proveedor_id=seed_proveedor_pcp["id"],
        body=RegistrarResultadoNegociacion(
            resultado="precio_obtenido",
            precio_unitario=Decimal("123.45"),
            mantenimiento_hasta=vencimiento,
        ),
        usuario_id=seed_usuario_sistema["id"],
    )

    try:
        assert resultado["resultado"] == "precio_obtenido"
        assert resultado["precio_proveedor_id"] is not None
        # Nunca una segunda fila: uq_ppr_renglon_prov + upsert transicionan
        # la misma fila que dejó seleccionar_proveedores (PR5).
        en_bd_resultados = (
            service_client.table("pcp_renglon_resultados")
            .select("id")
            .eq("pcp_renglon_id", renglon["id"])
            .eq("proveedor_id", seed_proveedor_pcp["id"])
            .execute()
            .data
        )
        assert len(en_bd_resultados) == 1

        precio = (
            service_client.table("precios_proveedor")
            .select("*")
            .eq("id", resultado["precio_proveedor_id"])
            .execute()
            .data[0]
        )
        assert precio["item_proceso_id"] == seed_item_proceso["id"]
        assert precio["producto_id"] == seed_producto["id"]
        assert precio["proveedor_id"] == seed_proveedor_pcp["id"]
        assert Decimal(str(precio["precio_unitario"])) == Decimal("123.45")
        assert precio["mantenimiento_hasta"] == vencimiento.isoformat()

        en_bd_precios = (
            service_client.table("precios_proveedor")
            .select("id")
            .eq("item_proceso_id", seed_item_proceso["id"])
            .execute()
            .data
        )
        assert len(en_bd_precios) == 1
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()


# ---------------------------------------------------------------------------
# D6 -- registrar_resultado escribe un evento resultado_registrado en
# pcp_historial (append-only, nunca precio/costo crudo en el payload)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_registrar_resultado_escribe_evento_resultado_registrado_en_pcp_historial(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(resultado="no_cotiza", motivo="sin stock"),
            usuario_id=seed_usuario_sistema["id"],
        )

        eventos = (
            service_client.table("pcp_historial")
            .select("*")
            .eq("pcp_id", pcp["id"])
            .eq("tipo_evento", "resultado_registrado")
            .execute()
            .data
        )
        assert len(eventos) == 1
        evento = eventos[0]
        assert evento["pcp_renglon_id"] == renglon["id"]
        assert evento["payload"]["proveedor_id"] == seed_proveedor_pcp["id"]
        assert evento["payload"]["resultado"] == "no_cotiza"
        assert evento["usuario_id"] == seed_usuario_sistema["id"]
        assert evento["created_at"] is not None
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_registrar_resultado_precio_obtenido_sin_producto_matcheado_lanza_validation_error(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_sin_producto,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso_sin_producto["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        with pytest.raises(ServiceValidationError):
            registrar_resultado(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp["id"],
                pcp_renglon_id=renglon["id"],
                proveedor_id=seed_proveedor_pcp["id"],
                body=RegistrarResultadoNegociacion(
                    resultado="precio_obtenido",
                    precio_unitario=Decimal("10.00"),
                    mantenimiento_hasta=date.today() + timedelta(days=30),
                ),
                usuario_id=seed_usuario_sistema["id"],
            )

        en_bd = (
            service_client.table("precios_proveedor")
            .select("id")
            .eq("item_proceso_id", seed_item_proceso_sin_producto["id"])
            .execute()
            .data
        )
        assert en_bd == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# 7.3 -- condiciones de pago vía condicion_pago_id/forma_pago_id, nunca texto
# libre ni un id que no pertenezca a la droguería
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_registrar_resultado_referencia_condicion_y_forma_pago_reales(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
    seed_condicion_pago_pcp_factory,
    seed_forma_pago_pcp_factory,
):
    condicion = seed_condicion_pago_pcp_factory()
    forma = seed_forma_pago_pcp_factory()
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        resultado = registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(
                resultado="precio_obtenido",
                precio_unitario=Decimal("50.00"),
                mantenimiento_hasta=date.today() + timedelta(days=15),
                condicion_pago_id=condicion["id"],
                forma_pago_id=forma["id"],
            ),
            usuario_id=seed_usuario_sistema["id"],
        )

        precio = (
            service_client.table("precios_proveedor")
            .select("*")
            .eq("id", resultado["precio_proveedor_id"])
            .execute()
            .data[0]
        )
        assert precio["condicion_pago_id"] == condicion["id"]
        assert precio["forma_pago_id"] == forma["id"]
        # D5: plazo_pago_dias (deprecado) nunca se escribe desde código nuevo.
        assert precio["plazo_pago_dias"] is None
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()
        service_client.table("condiciones_pago").delete().eq("id", condicion["id"]).execute()
        service_client.table("formas_pago").delete().eq("id", forma["id"]).execute()


@pytest.mark.integration
def test_registrar_resultado_con_condicion_pago_de_otra_drogueria_lanza_validation_error(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    otra_drogueria_id = "00000000-0000-0000-0000-000000000000"
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        with pytest.raises(ServiceValidationError):
            registrar_resultado(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp["id"],
                pcp_renglon_id=renglon["id"],
                proveedor_id=seed_proveedor_pcp["id"],
                body=RegistrarResultadoNegociacion(
                    resultado="precio_obtenido",
                    precio_unitario=Decimal("10.00"),
                    mantenimiento_hasta=date.today() + timedelta(days=30),
                    condicion_pago_id=otra_drogueria_id,
                ),
                usuario_id=seed_usuario_sistema["id"],
            )

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


# ---------------------------------------------------------------------------
# 7.4 -- no_cotiza no requiere ni almacena precio; no bloquea a otro
# proveedor del mismo renglón
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_registrar_resultado_no_cotiza_no_requiere_ni_almacena_precio(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        resultado = registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(resultado="no_cotiza", motivo="Sin stock"),
            usuario_id=seed_usuario_sistema["id"],
        )

        assert resultado["resultado"] == "no_cotiza"
        assert resultado["precio_proveedor_id"] is None
        assert resultado["motivo"] == "Sin stock"

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
def test_no_cotiza_no_bloquea_precio_obtenido_de_otro_proveedor_en_el_mismo_renglon(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedores_pcp_factory,
):
    proveedor_p, proveedor_q = seed_proveedores_pcp_factory(2)
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[proveedor_p["id"], proveedor_q["id"]],
    )

    try:
        resultado_p = registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=proveedor_p["id"],
            body=RegistrarResultadoNegociacion(resultado="no_cotiza"),
            usuario_id=seed_usuario_sistema["id"],
        )
        assert resultado_p["resultado"] == "no_cotiza"

        resultado_q = registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=proveedor_q["id"],
            body=RegistrarResultadoNegociacion(
                resultado="precio_obtenido",
                precio_unitario=Decimal("99.00"),
                mantenimiento_hasta=date.today() + timedelta(days=10),
            ),
            usuario_id=seed_usuario_sistema["id"],
        )
        assert resultado_q["resultado"] == "precio_obtenido"
        assert resultado_q["precio_proveedor_id"] is not None

        # El no_cotiza de P sigue intacto: registrar el resultado de Q no lo
        # tocó (fila distinta, misma uq_ppr_renglon_prov por proveedor).
        actual_p = obtener_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=proveedor_p["id"],
        )
        assert actual_p["resultado"] == "no_cotiza"
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()


def test_no_cotiza_rechaza_cualquier_valor_de_precio_o_condiciones():
    with pytest.raises(PydanticValidationError):
        RegistrarResultadoNegociacion(resultado="no_cotiza", precio_unitario=Decimal("1"))
    with pytest.raises(PydanticValidationError):
        RegistrarResultadoNegociacion(
            resultado="no_cotiza", mantenimiento_hasta=date.today() + timedelta(days=1)
        )


def test_precio_obtenido_requiere_precio_y_mantenimiento_hasta():
    with pytest.raises(PydanticValidationError):
        RegistrarResultadoNegociacion(resultado="precio_obtenido")
    with pytest.raises(PydanticValidationError):
        RegistrarResultadoNegociacion(resultado="precio_obtenido", precio_unitario=Decimal("1"))


# ---------------------------------------------------------------------------
# 7.5 -- invariante de aislamiento: costos_productos y otros renglones nunca
# se tocan al registrar un resultado
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_registrar_resultado_no_modifica_costos_productos(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    costo = (
        service_client.table("costos_productos")
        .insert(
            {
                "producto_id": seed_producto["id"],
                "drogueria_id": seed_drogueria["id"],
                "costo_unitario": "100.00",
                "fecha_desde": date.today().isoformat(),
            }
        )
        .execute()
        .data[0]
    )
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(
                resultado="precio_obtenido",
                precio_unitario=Decimal("77.00"),
                mantenimiento_hasta=date.today() + timedelta(days=20),
            ),
            usuario_id=seed_usuario_sistema["id"],
        )

        costo_luego = (
            service_client.table("costos_productos").select("*").eq("id", costo["id"]).execute().data[0]
        )
        assert Decimal(str(costo_luego["costo_unitario"])) == Decimal("100.00")
        assert costo_luego["fecha_hasta"] is None
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()
        service_client.table("costos_productos").delete().eq("id", costo["id"]).execute()


@pytest.mark.integration
def test_registrar_resultado_no_afecta_precios_proveedor_de_otro_renglon(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    # Dos renglones (A, B) sobre el mismo producto, item_proceso_id distinto.
    item_a = seed_item_proceso_factory(numero_renglon=1)
    item_b = seed_item_proceso_factory(numero_renglon=2)
    presupuesto = seed_presupuesto_factory()

    pcp, renglon_a = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=item_a["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    renglon_b = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item_b["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon_b["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon_a["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(
                resultado="precio_obtenido",
                precio_unitario=Decimal("55.00"),
                mantenimiento_hasta=date.today() + timedelta(days=20),
            ),
            usuario_id=seed_usuario_sistema["id"],
        )

        precios_a = (
            service_client.table("precios_proveedor")
            .select("id")
            .eq("item_proceso_id", item_a["id"])
            .execute()
            .data
        )
        precios_b = (
            service_client.table("precios_proveedor")
            .select("id")
            .eq("item_proceso_id", item_b["id"])
            .execute()
            .data
        )
        assert len(precios_a) == 1
        assert precios_b == []

        resultado_b = obtener_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon_b["id"],
            proveedor_id=seed_proveedor_pcp["id"],
        )
        assert resultado_b["resultado"] == "sin_respuesta"
        assert resultado_b["precio_proveedor_id"] is None
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", item_a["id"]
        ).execute()


# ---------------------------------------------------------------------------
# 7.6 -- ventana de vigencia: un mantenimiento_hasta vencido no es válido
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_precio_con_mantenimiento_hasta_vencido_no_es_considerado_valido(
    service_client, seed_drogueria, seed_producto, seed_proveedor_pcp, seed_item_proceso
):
    """El servicio nunca puede escribir un precio nacido vencido en el flujo
    normal (`ck_pp_mant CHECK (mantenimiento_hasta >= fecha_oferta)`, y
    `fecha_oferta` toma `DEFAULT CURRENT_DATE` -- ver docstring de
    negociacion/service.py). Este test simula, con un INSERT directo, una
    fila vieja cuya ventana ya venció (fecha_oferta = mantenimiento_hasta =
    hace 30 días, satisface el CHECK) -- exactamente el escenario de la spec
    ("Expired maintenance window is not considered valid"): la vigencia es
    una preocupación de lectura, ya resuelta por
    `pricing/repository.py::buscar_precio_especial_puntual` sin cambios."""
    hace_30_dias = (date.today() - timedelta(days=30)).isoformat()
    vencido = (
        service_client.table("precios_proveedor")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "proveedor_id": seed_proveedor_pcp["id"],
                "producto_id": seed_producto["id"],
                "item_proceso_id": seed_item_proceso["id"],
                "precio_unitario": "42.00",
                "fecha_oferta": hace_30_dias,
                "mantenimiento_hasta": hace_30_dias,
            }
        )
        .execute()
        .data[0]
    )

    try:
        resultado = buscar_precio_especial_puntual(
            service_client, item_proceso_id=seed_item_proceso["id"], cantidad=Decimal("1")
        )
        assert resultado is None
    finally:
        service_client.table("precios_proveedor").delete().eq("id", vencido["id"]).execute()


# ---------------------------------------------------------------------------
# PCP frontend backend prerequisite -- persisted, non-exclusive selection
# ---------------------------------------------------------------------------


def test_actualizar_seleccion_rechaza_campos_adicionales():
    assert ActualizarSeleccionNegociacion(seleccionado=True).seleccionado is True
    with pytest.raises(PydanticValidationError):
        ActualizarSeleccionNegociacion(seleccionado=False, resultado="no_cotiza")


@pytest.mark.integration
def test_actualizar_seleccion_persiste_default_toggle_y_no_cotiza(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    try:
        assert obtener_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
        )["seleccionado"] is False
        with pytest.raises(NotFoundError):
            actualizar_seleccion(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp["id"],
                pcp_renglon_id=renglon["id"],
                proveedor_id="00000000-0000-0000-0000-000000000000",
                seleccionado=True,
                usuario_id=seed_usuario_sistema["id"],
            )
        registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(resultado="no_cotiza", motivo="Sin stock"),
            usuario_id=seed_usuario_sistema["id"],
        )
        assert actualizar_seleccion(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            seleccionado=True,
            usuario_id=seed_usuario_sistema["id"],
        )["seleccionado"] is True
        assert actualizar_seleccion(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            seleccionado=False,
            usuario_id=seed_usuario_sistema["id"],
        )["seleccionado"] is False
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# PCP frontend backend gap -- ResultadoNegociacionOut read model must join
# precios_proveedor (precio_unitario, cantidad_minima/maxima,
# mantenimiento_hasta, condicion_pago_id, forma_pago_id) instead of exposing
# only the precio_proveedor_id FK, per design.md "Comparison Table".
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_obtener_resultado_precio_obtenido_incluye_precio_y_condiciones_joined(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
    seed_condicion_pago_pcp_factory,
    seed_forma_pago_pcp_factory,
):
    condicion = seed_condicion_pago_pcp_factory()
    forma = seed_forma_pago_pcp_factory()
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    vencimiento = date.today() + timedelta(days=30)

    try:
        registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(
                resultado="precio_obtenido",
                precio_unitario=Decimal("123.45"),
                cantidad_minima=Decimal("1"),
                cantidad_maxima=Decimal("100"),
                mantenimiento_hasta=vencimiento,
                condicion_pago_id=condicion["id"],
                forma_pago_id=forma["id"],
            ),
            usuario_id=seed_usuario_sistema["id"],
        )

        resultado = obtener_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
        )

        assert Decimal(str(resultado["precio_unitario"])) == Decimal("123.45")
        assert Decimal(str(resultado["cantidad_minima"])) == Decimal("1")
        assert Decimal(str(resultado["cantidad_maxima"])) == Decimal("100")
        assert resultado["mantenimiento_hasta"] == vencimiento.isoformat()
        assert resultado["condicion_pago_id"] == condicion["id"]
        assert resultado["forma_pago_id"] == forma["id"]
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()
        service_client.table("condiciones_pago").delete().eq("id", condicion["id"]).execute()
        service_client.table("formas_pago").delete().eq("id", forma["id"]).execute()


@pytest.mark.integration
def test_obtener_resultado_no_cotiza_no_incluye_precio_ni_condiciones(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(resultado="no_cotiza", motivo="Sin stock"),
            usuario_id=seed_usuario_sistema["id"],
        )

        resultado = obtener_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
        )

        assert resultado["precio_unitario"] is None
        assert resultado["cantidad_minima"] is None
        assert resultado["cantidad_maxima"] is None
        assert resultado["mantenimiento_hasta"] is None
        assert resultado["condicion_pago_id"] is None
        assert resultado["forma_pago_id"] is None
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_seleccion_es_no_exclusiva_y_el_agregado_deduplica_renglones(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedores_pcp_factory,
):
    proveedor_a, proveedor_b = seed_proveedores_pcp_factory(2)
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[proveedor_a["id"], proveedor_b["id"]],
    )
    try:
        for proveedor in (proveedor_a, proveedor_b):
            actualizar_seleccion(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp["id"],
                pcp_renglon_id=renglon["id"],
                proveedor_id=proveedor["id"],
                seleccionado=True,
                usuario_id=seed_usuario_sistema["id"],
            )
        assert listar_renglones_seleccionados(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
        ) == [renglon["id"]]
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# Corrective Rerun -- listar_selecciones_agrupables (renglón×proveedor pairs
# for grouping into consultations; see openspec/changes/pcp-frontend
# apply-progress.md "Corrective Rerun -- Consultas grouping scope")
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listar_selecciones_agrupables_devuelve_un_par_por_proveedor_seleccionado(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedores_pcp_factory,
):
    proveedor_a, proveedor_b = seed_proveedores_pcp_factory(2)
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[proveedor_a["id"], proveedor_b["id"]],
    )
    try:
        for proveedor in (proveedor_a, proveedor_b):
            actualizar_seleccion(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp["id"],
                pcp_renglon_id=renglon["id"],
                proveedor_id=proveedor["id"],
                seleccionado=True,
                usuario_id=seed_usuario_sistema["id"],
            )
        pares = listar_selecciones_agrupables(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
        )
        assert sorted(pares, key=lambda par: par["proveedor_id"]) == sorted(
            [
                {"pcp_renglon_id": renglon["id"], "proveedor_id": proveedor_a["id"]},
                {"pcp_renglon_id": renglon["id"], "proveedor_id": proveedor_b["id"]},
            ],
            key=lambda par: par["proveedor_id"],
        )
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_listar_selecciones_agrupables_omite_renglon_sin_seleccion(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    try:
        assert listar_selecciones_agrupables(
            service_client,
            pcp_id=pcp["id"],
            drogueria_id=seed_drogueria["id"],
        ) == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# Code review finding -- registrar_resultado/obtener_resultado/
# actualizar_seleccion recibían pcp_id en la URL pero nunca lo comparaban
# contra el pcp_id real del renglón (solo drogueria_id/tenant se validaba).
# Un renglón de la PCP A, referenciado con el pcp_id de la PCP B, operaba
# igual -- el pcp_id de la URL era decorativo, no aplicado.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_registrar_resultado_rechaza_pcp_id_que_no_es_dueno_del_renglon(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto_a = seed_presupuesto_factory()
    presupuesto_b = seed_presupuesto_factory()
    pcp_a, renglon_a = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto_a["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    pcp_b = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto_b["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        with pytest.raises(NotFoundError):
            registrar_resultado(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp_b["id"],
                pcp_renglon_id=renglon_a["id"],
                proveedor_id=seed_proveedor_pcp["id"],
                body=RegistrarResultadoNegociacion(
                    resultado="precio_obtenido",
                    precio_unitario=Decimal("10.00"),
                    mantenimiento_hasta=date.today() + timedelta(days=10),
                ),
                usuario_id=seed_usuario_sistema["id"],
            )
        en_bd = (
            service_client.table("precios_proveedor")
            .select("id")
            .eq("item_proceso_id", seed_item_proceso["id"])
            .execute()
            .data
        )
        assert en_bd == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp_a["id"]).execute()
        service_client.table("pcp").delete().eq("id", pcp_b["id"]).execute()


@pytest.mark.integration
def test_obtener_resultado_rechaza_pcp_id_que_no_es_dueno_del_renglon(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto_a = seed_presupuesto_factory()
    presupuesto_b = seed_presupuesto_factory()
    pcp_a, renglon_a = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto_a["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    pcp_b = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto_b["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        with pytest.raises(NotFoundError):
            obtener_resultado(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp_b["id"],
                pcp_renglon_id=renglon_a["id"],
                proveedor_id=seed_proveedor_pcp["id"],
            )
    finally:
        service_client.table("pcp").delete().eq("id", pcp_a["id"]).execute()
        service_client.table("pcp").delete().eq("id", pcp_b["id"]).execute()


@pytest.mark.integration
def test_actualizar_seleccion_rechaza_pcp_id_que_no_es_dueno_del_renglon(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto_a = seed_presupuesto_factory()
    presupuesto_b = seed_presupuesto_factory()
    pcp_a, renglon_a = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto_a["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    pcp_b = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto_b["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        with pytest.raises(NotFoundError):
            actualizar_seleccion(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp_b["id"],
                pcp_renglon_id=renglon_a["id"],
                proveedor_id=seed_proveedor_pcp["id"],
                seleccionado=True,
                usuario_id=seed_usuario_sistema["id"],
            )
        fila = (
            service_client.table("pcp_renglon_resultados")
            .select("seleccionado")
            .eq("pcp_renglon_id", renglon_a["id"])
            .execute()
            .data[0]
        )
        assert fila["seleccionado"] is False
    finally:
        service_client.table("pcp").delete().eq("id", pcp_a["id"]).execute()
        service_client.table("pcp").delete().eq("id", pcp_b["id"]).execute()


# ---------------------------------------------------------------------------
# Code review finding -- listar_resultados_renglon: lectura batched (un solo
# round trip) para todos los proveedores de un renglón, reemplazando el
# fan-out de N llamados a obtener_resultado que el frontend hacía antes.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listar_resultados_renglon_devuelve_todos_los_proveedores_en_un_llamado(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedores_pcp_factory,
):
    proveedor_a, proveedor_b = seed_proveedores_pcp_factory(2)
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[proveedor_a["id"], proveedor_b["id"]],
    )
    try:
        registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=proveedor_a["id"],
            body=RegistrarResultadoNegociacion(
                resultado="precio_obtenido",
                precio_unitario=Decimal("42.00"),
                mantenimiento_hasta=date.today() + timedelta(days=10),
            ),
            usuario_id=seed_usuario_sistema["id"],
        )
        registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=proveedor_b["id"],
            body=RegistrarResultadoNegociacion(resultado="no_cotiza", motivo="Sin stock"),
            usuario_id=seed_usuario_sistema["id"],
        )

        resultados = listar_resultados_renglon(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            pcp_renglon_id=renglon["id"],
        )

        por_proveedor = {fila["proveedor_id"]: fila for fila in resultados}
        assert len(resultados) == 2
        assert por_proveedor[proveedor_a["id"]]["resultado"] == "precio_obtenido"
        assert Decimal(str(por_proveedor[proveedor_a["id"]]["precio_unitario"])) == Decimal("42.00")
        assert por_proveedor[proveedor_b["id"]]["resultado"] == "no_cotiza"
        assert por_proveedor[proveedor_b["id"]]["precio_unitario"] is None
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()


@pytest.mark.integration
def test_listar_resultados_renglon_rechaza_pcp_id_que_no_es_dueno_del_renglon(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto_a = seed_presupuesto_factory()
    presupuesto_b = seed_presupuesto_factory()
    pcp_a, renglon_a = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto_a["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    pcp_b = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto_b["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        with pytest.raises(NotFoundError):
            listar_resultados_renglon(
                service_client,
                drogueria_id=seed_drogueria["id"],
                pcp_id=pcp_b["id"],
                pcp_renglon_id=renglon_a["id"],
            )
    finally:
        service_client.table("pcp").delete().eq("id", pcp_a["id"]).execute()
        service_client.table("pcp").delete().eq("id", pcp_b["id"]).execute()
