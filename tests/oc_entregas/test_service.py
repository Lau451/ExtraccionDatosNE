"""tests/oc_entregas/test_service.py -- planificación de entregas después del
matching (odd/tasks/oc-entregas-planificacion.md, T3; design.md D1/D8 del
cambio orden-compra).
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.presupuestacion.core.exceptions import ConflictError, NotFoundError, ValidationError
from services.presupuestacion.extraccion import repository as extraccion_repo
from services.presupuestacion.oc_entregas import repository as repo
from services.presupuestacion.oc_entregas import service
from services.presupuestacion.oc_entregas.models import EntregaItemPlanIn, EntregaPlanIn

# =============================================================================
# sugerir_plan_renglon -- función pura (T3 § plan_sugerido). Sin cliente
# Supabase: packs enteros repartidos con repartir_cantidad (D8), resto a la
# ÚLTIMA entrega. Ejemplos literales de la tarea.
# =============================================================================


def test_sugerir_plan_renglon_100_x25_n3_da_50_25_25():
    resultado = service.sugerir_plan_renglon(Decimal("100"), 25, 3)
    assert resultado == [Decimal("50"), Decimal("25"), Decimal("25")]


def test_sugerir_plan_renglon_110_x25_n3_da_50_25_35():
    resultado = service.sugerir_plan_renglon(Decimal("110"), 25, 3)
    assert resultado == [Decimal("50"), Decimal("25"), Decimal("35")]


def test_sugerir_plan_renglon_sin_pack_conocido_usa_repartir_cantidad_liso():
    resultado = service.sugerir_plan_renglon(Decimal("10"), None, 3)
    assert resultado == [Decimal("4"), Decimal("3"), Decimal("3")]


def test_sugerir_plan_renglon_pack_cero_o_negativo_se_trata_como_desconocido():
    assert service.sugerir_plan_renglon(Decimal("10"), 0, 3) == [
        Decimal("4"),
        Decimal("3"),
        Decimal("3"),
    ]


def test_sugerir_plan_renglon_menos_de_un_pack_completo_todo_va_de_resto_al_final():
    # cantidad=10, u=25 -> 0 packs enteros; los 10 son puro "resto" -> a la
    # última entrega, ninguna intermedia queda con una cantidad fantasma.
    resultado = service.sugerir_plan_renglon(Decimal("10"), 25, 3)
    assert resultado == [Decimal("0"), Decimal("0"), Decimal("10")]


@pytest.mark.parametrize(
    "cantidad, unidades, entregas",
    [
        ("100", 25, 3),
        ("110", 25, 3),
        ("10", None, 4),
        ("37", 5, 2),
        ("1", 25, 1),
        ("0", 25, 3),
    ],
)
def test_sugerir_plan_renglon_invariante_suma_igual_a_cantidad(cantidad, unidades, entregas):
    resultado = service.sugerir_plan_renglon(Decimal(cantidad), unidades, entregas)
    assert len(resultado) == entregas
    assert sum(resultado) == Decimal(cantidad)


# =============================================================================
# Helpers in-memory (sin DB) -- mismo criterio que tests/oc_presupuesto.
# =============================================================================


def _oc_item(
    id_: str,
    *,
    numero_renglon: int = 1,
    numero_renglon_documento: str | None = None,
    descripcion: str = "Renglón de test",
    cantidad: str = "100",
    producto_id: str | None = None,
    presupuesto_item_id: str | None = "pi-1",
    vinculo_descartado: bool = False,
) -> dict:
    return {
        "id": id_,
        "orden_compra_id": "oc-1",
        "numero_renglon": numero_renglon,
        "numero_renglon_documento": numero_renglon_documento,
        "descripcion": descripcion,
        "cantidad": cantidad,
        "producto_id": producto_id,
        "presupuesto_item_id": presupuesto_item_id,
        "vinculo_descartado": vinculo_descartado,
    }


def _oc(**overrides) -> dict:
    base = {"id": "oc-1", "drogueria_id": "d1", "cliente_id": "cli-1", "numero_oc": "OC-1", "cantidad_entregas": 3}
    base.update(overrides)
    return base


def _entrega_in(numero_entrega: int, items: list[tuple[str, str]], fecha=None) -> EntregaPlanIn:
    return EntregaPlanIn(
        numero_entrega=numero_entrega,
        fecha_entrega_planificada=fecha,
        items=[EntregaItemPlanIn(oc_item_id=oc_item_id, cantidad=Decimal(cantidad)) for oc_item_id, cantidad in items],
    )


# =============================================================================
# obtener_planificacion -- gate y contexto (GET).
# =============================================================================


def test_obtener_planificacion_oc_inexistente_da_not_found(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: None)
    with pytest.raises(NotFoundError):
        service.obtener_planificacion(MagicMock(), orden_compra_id="oc-x", drogueria_id="d1")


def test_obtener_planificacion_oc_de_otra_drogueria_da_not_found_sin_confirmar_existencia(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _oc(drogueria_id="otra"))
    with pytest.raises(NotFoundError):
        service.obtener_planificacion(MagicMock(), orden_compra_id="oc-1", drogueria_id="d1")


def test_obtener_planificacion_con_pendientes_no_puede_planificar(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _oc())
    monkeypatch.setattr(
        repo,
        "listar_oc_items",
        lambda client, **kw: [
            _oc_item("i1", presupuesto_item_id="pi-1"),
            _oc_item("i2", numero_renglon=2, presupuesto_item_id=None, vinculo_descartado=False),
        ],
    )
    monkeypatch.setattr(repo, "listar_productos_por_ids", lambda client, **kw: [])
    monkeypatch.setattr(repo, "listar_entregas_oc", lambda client, **kw: [])
    monkeypatch.setattr(repo, "listar_entregas_oc_items", lambda client, **kw: [])

    resultado = service.obtener_planificacion(MagicMock(), orden_compra_id="oc-1", drogueria_id="d1")

    assert resultado.puede_planificar is False
    assert resultado.pendientes == 1
    assert "pendiente" in resultado.motivo
    assert resultado.plan_sugerido == []  # sin sugerencia mientras no se puede planificar


def test_obtener_planificacion_sin_renglones_confirmados_no_puede_planificar(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _oc())
    monkeypatch.setattr(
        repo,
        "listar_oc_items",
        lambda client, **kw: [_oc_item("i1", presupuesto_item_id=None, vinculo_descartado=True)],
    )
    monkeypatch.setattr(repo, "listar_productos_por_ids", lambda client, **kw: [])
    monkeypatch.setattr(repo, "listar_entregas_oc", lambda client, **kw: [])
    monkeypatch.setattr(repo, "listar_entregas_oc_items", lambda client, **kw: [])

    resultado = service.obtener_planificacion(MagicMock(), orden_compra_id="oc-1", drogueria_id="d1")

    assert resultado.puede_planificar is False
    assert resultado.descartados == 1
    assert "no tiene renglones confirmados" in resultado.motivo


def test_obtener_planificacion_con_plan_bloqueado_no_puede_replanificar(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _oc())
    monkeypatch.setattr(repo, "listar_oc_items", lambda client, **kw: [_oc_item("i1")])
    monkeypatch.setattr(repo, "listar_productos_por_ids", lambda client, **kw: [])
    monkeypatch.setattr(
        repo,
        "listar_entregas_oc",
        lambda client, **kw: [{"id": "e1", "numero_entrega": 1, "fecha_entrega_planificada": None, "estado": "entregada"}],
    )
    monkeypatch.setattr(repo, "listar_entregas_oc_items", lambda client, **kw: [])

    resultado = service.obtener_planificacion(MagicMock(), orden_compra_id="oc-1", drogueria_id="d1")

    assert resultado.puede_planificar is False
    assert "no se puede replanificar" in resultado.motivo


def test_obtener_planificacion_ok_arma_renglones_producto_y_plan_sugerido(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _oc(cantidad_entregas=3))
    monkeypatch.setattr(
        repo,
        "listar_oc_items",
        lambda client, **kw: [
            _oc_item("i1", cantidad="110", producto_id="prod-1"),
            _oc_item("i2", numero_renglon=2, cantidad="7", vinculo_descartado=True, presupuesto_item_id=None),
        ],
    )
    monkeypatch.setattr(
        repo,
        "listar_productos_por_ids",
        lambda client, **kw: [{"id": "prod-1", "nombre": "Producto x25", "unidades_por_presentacion": 25}],
    )
    monkeypatch.setattr(repo, "listar_entregas_oc", lambda client, **kw: [])
    monkeypatch.setattr(repo, "listar_entregas_oc_items", lambda client, **kw: [])

    resultado = service.obtener_planificacion(MagicMock(), orden_compra_id="oc-1", drogueria_id="d1")

    assert resultado.puede_planificar is True
    assert resultado.motivo is None
    assert resultado.descartados == 1
    assert len(resultado.renglones) == 1
    renglon = resultado.renglones[0]
    assert renglon.producto_nombre == "Producto x25"
    assert renglon.unidades_por_presentacion == 25
    assert resultado.cantidad_entregas_sugerida == 3
    assert len(resultado.plan_sugerido) == 1
    assert resultado.plan_sugerido[0].cantidades == [Decimal("50"), Decimal("25"), Decimal("35")]


def test_obtener_planificacion_arma_plan_actual_desde_entregas_existentes(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _oc())
    monkeypatch.setattr(repo, "listar_oc_items", lambda client, **kw: [_oc_item("i1")])
    monkeypatch.setattr(repo, "listar_productos_por_ids", lambda client, **kw: [])
    monkeypatch.setattr(
        repo,
        "listar_entregas_oc",
        lambda client, **kw: [
            {"id": "e1", "numero_entrega": 1, "fecha_entrega_planificada": "2026-01-01", "estado": "pendiente"}
        ],
    )
    monkeypatch.setattr(
        repo,
        "listar_entregas_oc_items",
        lambda client, **kw: [{"entrega_oc_id": "e1", "oc_item_id": "i1", "cantidad_planificada": "100"}],
    )

    resultado = service.obtener_planificacion(MagicMock(), orden_compra_id="oc-1", drogueria_id="d1")

    assert len(resultado.plan_actual) == 1
    assert resultado.plan_actual[0].items[0].oc_item_id == "i1"
    assert resultado.plan_actual[0].items[0].cantidad_planificada == Decimal("100")


# =============================================================================
# planificar_entregas -- gate, validaciones, reemplazo/lock, advertencias (PUT).
# =============================================================================


def _mockear_lectura_basica(monkeypatch, *, oc_items, entregas_existentes=None, productos=None):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: _oc())
    monkeypatch.setattr(repo, "listar_oc_items", lambda client, **kw: oc_items)
    monkeypatch.setattr(repo, "listar_entregas_oc", lambda client, **kw: entregas_existentes or [])
    monkeypatch.setattr(repo, "listar_productos_por_ids", lambda client, **kw: productos or [])


def test_planificar_oc_inexistente_da_not_found(monkeypatch):
    monkeypatch.setattr(repo, "buscar_orden_compra", lambda client, **kw: None)
    with pytest.raises(NotFoundError):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-x", drogueria_id="d1", usuario_id="u1", entregas=[]
        )


def test_planificar_sin_entregas_en_el_body_da_validation_error(monkeypatch):
    _mockear_lectura_basica(monkeypatch, oc_items=[_oc_item("i1")])
    with pytest.raises(ValidationError):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=[]
        )


def test_planificar_con_renglon_pendiente_da_conflict_409(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch,
        oc_items=[
            _oc_item("i1"),
            _oc_item("i2", numero_renglon=2, presupuesto_item_id=None, vinculo_descartado=False),
        ],
    )
    entregas = [_entrega_in(1, [("i1", "100")])]
    with pytest.raises(ConflictError, match="pendiente"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


def test_planificar_sin_renglones_confirmados_da_conflict_409(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch, oc_items=[_oc_item("i1", presupuesto_item_id=None, vinculo_descartado=True)]
    )
    entregas = [_entrega_in(1, [("i1", "100")])]
    with pytest.raises(ConflictError, match="confirmados"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


def test_planificar_con_plan_bloqueado_da_conflict_409(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch,
        oc_items=[_oc_item("i1", cantidad="100")],
        entregas_existentes=[
            {"id": "e1", "numero_entrega": 1, "fecha_entrega_planificada": None, "estado": "en_transito"}
        ],
    )
    entregas = [_entrega_in(1, [("i1", "100")])]
    with pytest.raises(ConflictError, match="bloqueado"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


@pytest.mark.parametrize(
    "numeros",
    [
        [1, 3],  # falta el 2
        [1, 1],  # repetido
        [0, 1],  # no empieza en 1
        [2, 3],  # no empieza en 1
    ],
)
def test_planificar_numeracion_no_1_a_n_consecutiva_da_validation_error(monkeypatch, numeros):
    _mockear_lectura_basica(monkeypatch, oc_items=[_oc_item("i1", cantidad="100")])
    entregas = [_entrega_in(n, [("i1", "50")]) for n in numeros]
    with pytest.raises(ValidationError, match="1\\.\\."):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


def test_planificar_item_ajeno_a_la_oc_da_validation_error(monkeypatch):
    _mockear_lectura_basica(monkeypatch, oc_items=[_oc_item("i1", cantidad="100")])
    entregas = [_entrega_in(1, [("i-ajeno", "100")])]
    with pytest.raises(ValidationError, match="no está confirmado"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


def test_planificar_item_descartado_no_puede_recibir_cantidad_da_validation_error(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch,
        oc_items=[
            _oc_item("i1", cantidad="100"),
            _oc_item("i2", numero_renglon=2, cantidad="7", presupuesto_item_id=None, vinculo_descartado=True),
        ],
    )
    entregas = [_entrega_in(1, [("i1", "100"), ("i2", "7")])]
    with pytest.raises(ValidationError, match="no está confirmado"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


def test_planificar_cantidad_negativa_da_validation_error(monkeypatch):
    _mockear_lectura_basica(monkeypatch, oc_items=[_oc_item("i1", cantidad="100")])
    entregas = [_entrega_in(1, [("i1", "-1")])]
    with pytest.raises(ValidationError, match="negativa"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


def test_planificar_entrega_con_todas_las_cantidades_en_cero_da_validation_error(monkeypatch):
    _mockear_lectura_basica(monkeypatch, oc_items=[_oc_item("i1", cantidad="100")])
    entregas = [_entrega_in(1, [("i1", "0")])]
    with pytest.raises(ValidationError, match="cero"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


def test_planificar_suma_no_coincide_con_cantidad_del_renglon_da_validation_error(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch, oc_items=[_oc_item("i1", cantidad="100", numero_renglon_documento="5")]
    )
    entregas = [_entrega_in(1, [("i1", "40")])]  # 40 != 100
    with pytest.raises(ValidationError, match="renglón 5"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )


def _mockear_escritura(monkeypatch):
    """Espía de los inserts/updates (T3 § reemplazo). Devuelve los espías
    para que cada test assert sobre lo que se llamó."""
    entregas_creadas: list[dict] = []
    items_insertados: list[list[dict]] = []
    borrados: list[str] = []
    actualizaciones: list[dict] = []

    def _crear_entrega_oc(client, fila):
        entregas_creadas.append(fila)
        return {"id": f"entrega-{len(entregas_creadas)}"}

    def _insertar_items(client, filas):
        items_insertados.append(filas)
        return filas

    def _borrar(client, **kw):
        borrados.append(kw["orden_compra_id"])

    def _actualizar(client, **kw):
        actualizaciones.append(kw)
        return {"id": kw["orden_compra_id"], "cantidad_entregas": kw["cantidad_entregas"]}

    monkeypatch.setattr(extraccion_repo, "crear_entrega_oc", _crear_entrega_oc)
    monkeypatch.setattr(extraccion_repo, "insertar_entregas_oc_items", _insertar_items)
    monkeypatch.setattr(repo, "borrar_entregas_oc", _borrar)
    monkeypatch.setattr(repo, "actualizar_cantidad_entregas", _actualizar)
    return entregas_creadas, items_insertados, borrados, actualizaciones


def test_planificar_ok_crea_entregas_e_items_y_actualiza_cantidad_entregas(monkeypatch):
    _mockear_lectura_basica(monkeypatch, oc_items=[_oc_item("i1", cantidad="100")])
    entregas_creadas, items_insertados, borrados, actualizaciones = _mockear_escritura(monkeypatch)

    entregas = [_entrega_in(1, [("i1", "60")]), _entrega_in(2, [("i1", "40")])]
    resultado = service.planificar_entregas(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
    )

    assert borrados == []  # no había plan anterior -- nada que borrar
    assert len(entregas_creadas) == 2
    assert entregas_creadas[0]["numero_entrega"] == 1
    assert entregas_creadas[0]["estado"] == "pendiente"
    assert items_insertados[0][0]["cantidad_planificada"] == "60"
    assert items_insertados[0][0]["cantidad_entregada"] == "0"
    assert actualizaciones == [{"orden_compra_id": "oc-1", "cantidad_entregas": 2}]
    assert [e.numero_entrega for e in resultado.entregas] == [1, 2]
    assert resultado.advertencias == []


def test_planificar_ok_reemplaza_plan_pendiente_existente(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch,
        oc_items=[_oc_item("i1", cantidad="100")],
        entregas_existentes=[
            {"id": "e-vieja", "numero_entrega": 1, "fecha_entrega_planificada": None, "estado": "pendiente"}
        ],
    )
    entregas_creadas, items_insertados, borrados, actualizaciones = _mockear_escritura(monkeypatch)

    entregas = [_entrega_in(1, [("i1", "100")])]
    service.planificar_entregas(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
    )

    assert borrados == ["oc-1"]  # el plan viejo (pendiente) SÍ se reemplaza


def test_planificar_omite_items_en_cero_al_insertar_pero_los_valida(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch, oc_items=[_oc_item("i1", cantidad="100"), _oc_item("i2", numero_renglon=2, cantidad="0")]
    )
    _entregas_creadas, items_insertados, _borrados, _actualizaciones = _mockear_escritura(monkeypatch)

    # i2 tiene cantidad total 0 -- una entrega puede declararlo en 0 sin que
    # cuente para el chequeo de "todo en cero" (i1 en la misma entrega no es 0).
    entregas = [_entrega_in(1, [("i1", "100"), ("i2", "0")])]
    service.planificar_entregas(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
    )

    ids_insertados = {fila["oc_item_id"] for fila in items_insertados[0]}
    assert ids_insertados == {"i1"}  # i2 (cantidad 0) nunca se inserta


def test_planificar_advertencia_de_divisibilidad_no_bloquea_y_sugiere_multiplo_menor(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch,
        oc_items=[_oc_item("i1", cantidad="30", producto_id="prod-1")],
        productos=[{"id": "prod-1", "nombre": "Producto x25", "unidades_por_presentacion": 25}],
    )
    _mockear_escritura(monkeypatch)

    entregas = [_entrega_in(1, [("i1", "30")])]
    resultado = service.planificar_entregas(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
    )

    assert len(resultado.advertencias) == 1
    advertencia = resultado.advertencias[0]
    assert advertencia.oc_item_id == "i1"
    assert advertencia.cantidad_sugerida == Decimal("25")


def test_planificar_advertencia_cuando_multiplo_menor_es_cero_sugiere_una_unidad_de_pack(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch,
        oc_items=[_oc_item("i1", cantidad="10", producto_id="prod-1")],
        productos=[{"id": "prod-1", "nombre": "Producto x25", "unidades_por_presentacion": 25}],
    )
    _mockear_escritura(monkeypatch)

    entregas = [_entrega_in(1, [("i1", "10")])]
    resultado = service.planificar_entregas(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
    )

    assert resultado.advertencias[0].cantidad_sugerida == Decimal("25")


def test_planificar_multiplo_exacto_no_genera_advertencia(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch,
        oc_items=[_oc_item("i1", cantidad="50", producto_id="prod-1")],
        productos=[{"id": "prod-1", "nombre": "Producto x25", "unidades_por_presentacion": 25}],
    )
    _mockear_escritura(monkeypatch)

    entregas = [_entrega_in(1, [("i1", "50")])]
    resultado = service.planificar_entregas(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
    )

    assert resultado.advertencias == []


def test_planificar_falla_a_mitad_de_camino_compensa_borrando_lo_insertado(monkeypatch):
    _mockear_lectura_basica(
        monkeypatch, oc_items=[_oc_item("i1", cantidad="100"), _oc_item("i2", numero_renglon=2, cantidad="50")]
    )
    _entregas_creadas, _items, borrados, _actualizaciones = _mockear_escritura(monkeypatch)

    def _insertar_items_falla(client, filas):
        raise RuntimeError("insert de entregas_oc_items falló")

    monkeypatch.setattr(extraccion_repo, "insertar_entregas_oc_items", _insertar_items_falla)

    entregas = [_entrega_in(1, [("i1", "100"), ("i2", "50")])]
    with pytest.raises(RuntimeError, match="falló"):
        service.planificar_entregas(
            MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
        )

    assert borrados == ["oc-1"]  # compensación: no queda un plan a medio insertar


def test_planificar_nunca_llama_funciones_de_stock(monkeypatch):
    from services.presupuestacion.core import stock

    espia = MagicMock()
    monkeypatch.setattr(stock, "entregar_stock_producto", espia)
    _mockear_lectura_basica(monkeypatch, oc_items=[_oc_item("i1", cantidad="100")])
    _mockear_escritura(monkeypatch)

    entregas = [_entrega_in(1, [("i1", "100")])]
    service.planificar_entregas(
        MagicMock(), orden_compra_id="oc-1", drogueria_id="d1", usuario_id="u1", entregas=entregas
    )

    espia.assert_not_called()
